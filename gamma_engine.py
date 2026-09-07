from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import math
import requests
import pandas as pd

API_ROOT = "https://api.marketdata.app/v1"

@dataclass
class GammaConfig:
    min_dte: int = 20
    max_dte: int = 60
    strike_pct: float = 0.15
    contract_multiplier: int = 100

def _as_list(value, n=None):
    if isinstance(value, list):
        return value
    if n is None:
        return [value]
    return [value] * n

def fetch_option_chain(symbol, token):
    symbol = symbol.strip().upper()
    if not symbol:
        raise RuntimeError("Symbol is empty.")

    today = datetime.now(timezone.utc).date()
    cfg = GammaConfig()
    from_date = today + timedelta(days=cfg.min_dte)
    to_date = today + timedelta(days=cfg.max_dte)

    url = f"{API_ROOT}/options/chain/{symbol}/"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=60,
    )

    if response.status_code not in (200, 203):
        try:
            payload = response.json()
            message = payload.get("errmsg") or payload.get("message")
        except Exception:
            message = response.text
        raise RuntimeError(f"MarketData HTTP {response.status_code}: {message}")

    payload = response.json()

    if payload.get("s") == "error":
        raise RuntimeError(payload.get("errmsg", "Option-chain API error."))

    option_symbols = payload.get("optionSymbol", [])
    if not isinstance(option_symbols, list):
        option_symbols = [option_symbols]

    n = len(option_symbols)
    if n == 0:
        raise RuntimeError("No option-chain contracts returned by MarketData.")

    keys = ["optionSymbol", "expiration", "side", "strike", "openInterest", "gamma", "underlyingPrice"]
    cols = {}

    for key in keys:
        value = payload.get(key, [])
        value = _as_list(value, n)
        cols[key] = value if len(value) == n else [None] * n

    return pd.DataFrame(cols)

def normalize_chain(df, cfg):
    if df.empty:
        raise RuntimeError("Option-chain dataframe is empty.")

    out = df.copy()

    for col in ["strike", "openInterest", "gamma", "underlyingPrice"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    expiration_numeric = pd.to_numeric(out["expiration"], errors="coerce")

    if expiration_numeric.notna().mean() > 0.8:
        median_exp = expiration_numeric.dropna().median()
        unit = "ms" if median_exp > 10_000_000_000 else "s"
        out["expiration_dt"] = pd.to_datetime(expiration_numeric, unit=unit, errors="coerce", utc=True)
    else:
        out["expiration_dt"] = pd.to_datetime(out["expiration"], errors="coerce", utc=True)

    today = datetime.now(timezone.utc).date()

    out["dte"] = out["expiration_dt"].apply(
        lambda x: (x.date() - today).days if pd.notna(x) else None
    )

    spot_series = out["underlyingPrice"].dropna()
    if spot_series.empty:
        raise RuntimeError("Underlying price was not returned by MarketData.")

    spot = float(spot_series.iloc[0])

    out = out[
        out["dte"].notna()
        & (out["dte"] >= cfg.min_dte)
        & (out["dte"] <= cfg.max_dte)
        & out["strike"].notna()
        & (out["strike"] >= spot * (1 - cfg.strike_pct))
        & (out["strike"] <= spot * (1 + cfg.strike_pct))
    ].copy()

    if out.empty:
        raise RuntimeError(
            "No contracts remained after the DTE and strike filters. Try a wider DTE window or strike range."
        )

    out["oi"] = out["openInterest"].fillna(0).clip(lower=0)
    out["gamma_abs"] = out["gamma"].abs().fillna(0)

    side_text = out["side"].astype(str).str.lower().str.strip()
    sign = side_text.apply(
        lambda x: 1 if x.startswith("c") else -1 if x.startswith("p") else 0
    )

    out["gex"] = (
        sign
        * out["gamma_abs"]
        * out["oi"]
        * cfg.contract_multiplier
        * (spot ** 2)
        * 0.01
    )
    out["abs_gex"] = out["gex"].abs()

    return out, spot

def summarize_gamma(df, spot):
    if df.empty:
        raise RuntimeError("No contracts available for gamma summary.")

    by = (
        df.groupby("strike", as_index=False)
        .agg(net_gex=("gex", "sum"), abs_gex=("abs_gex", "sum"))
        .sort_values("strike")
        .reset_index(drop=True)
    )

    calls = (
        df[df["side"].astype(str).str.lower().str.startswith("c")]
        .groupby("strike", as_index=False)
        .agg(call_gex=("gex", "sum"))
    )

    puts = (
        df[df["side"].astype(str).str.lower().str.startswith("p")]
        .groupby("strike", as_index=False)
        .agg(put_gex=("gex", "sum"))
    )

    by = by.merge(calls, on="strike", how="left").merge(puts, on="strike", how="left")
    by["call_gex"] = by["call_gex"].fillna(0)
    by["put_gex"] = by["put_gex"].fillna(0)

    call_wall = math.nan
    put_wall = math.nan

    if (by["call_gex"] > 0).any():
        call_wall = float(by.loc[by["call_gex"].idxmax(), "strike"])

    if (by["put_gex"] < 0).any():
        put_wall = float(by.loc[by["put_gex"].idxmin(), "strike"])

    temp = by.copy()
    temp["cum_gex"] = temp["net_gex"].cumsum()

    gamma_flip = math.nan
    vals = temp[["strike", "cum_gex"]].values

    for i in range(1, len(vals)):
        s0, g0 = vals[i - 1]
        s1, g1 = vals[i]
        if g0 == 0:
            gamma_flip = float(s0)
            break
        if g0 * g1 < 0:
            gamma_flip = float(s0 + (0 - g0) * (s1 - s0) / (g1 - g0))
            break

    total = float(by["net_gex"].sum())
    regime = "POSITIVE GAMMA" if total > 0 else "NEGATIVE GAMMA"

    return {
        "spot": float(spot),
        "net_gex": total,
        "regime": regime,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_flip": gamma_flip,
        "by_strike": by,
    }
