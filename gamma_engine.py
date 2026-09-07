from dataclasses import dataclass
from datetime import datetime
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


def fetch_option_chain(symbol, token):
    url = f"{API_ROOT}/options/chain/{symbol.upper()}/"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    r = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    r.raise_for_status()

    p = r.json()

    if p.get("s") == "error":
        raise RuntimeError(
            p.get("errmsg", "Option-chain API error.")
        )

    option_symbols = p.get("optionSymbol", [])

    if not isinstance(option_symbols, list):
        option_symbols = [option_symbols]

    n = len(option_symbols)

    if n == 0:
        raise RuntimeError(
            "No option-chain contracts returned."
        )

    keys = [
        "optionSymbol",
        "expiration",
        "side",
        "strike",
        "openInterest",
        "gamma",
        "underlyingPrice"
    ]

    cols = {}

    for k in keys:
        v = p.get(k, [])

        if not isinstance(v, list):
            v = [v] * n

        if len(v) == n:
            cols[k] = v
        else:
            cols[k] = [None] * n

    return pd.DataFrame(cols)


def normalize_chain(df, cfg):
    out = df.copy()

    required = [
        "strike",
        "openInterest",
        "gamma",
        "underlyingPrice"
    ]

    for c in required:
        out[c] = pd.to_numeric(
            out[c],
            errors="coerce"
        )

    if pd.api.types.is_numeric_dtype(out["expiration"]):
        out["expiration_dt"] = pd.to_datetime(
            out["expiration"],
            unit="s",
            errors="coerce"
        )
    else:
        out["expiration_dt"] = pd.to_datetime(
            out["expiration"],
            errors="coerce"
        )

    today = datetime.utcnow().date()

    out["dte"] = out["expiration_dt"].apply(
        lambda x:
        (x.date() - today).days
        if pd.notna(x)
        else None
    )

    spot_series = out["underlyingPrice"].dropna()

    if spot_series.empty:
        raise RuntimeError(
            "Underlying price was not returned."
        )

    spot = float(
        spot_series.iloc[0]
    )

    out = out[
        (out["dte"] >= cfg.min_dte) &
        (out["dte"] <= cfg.max_dte) &
        (
            out["strike"] >=
            spot * (1 - cfg.strike_pct)
        ) &
        (
            out["strike"] <=
            spot * (1 + cfg.strike_pct)
        )
    ].copy()

    if out.empty:
        raise RuntimeError(
            "No contracts remained after DTE/strike filters."
        )

    out["oi"] = (
        out["openInterest"]
        .fillna(0)
    )

    out["gamma_abs"] = (
        out["gamma"]
        .abs()
        .fillna(0)
    )

    side_text = (
        out["side"]
        .astype(str)
        .str.lower()
    )

    sign = side_text.apply(
        lambda x: 1
        if x.startswith("c")
        else -1
        if x.startswith("p")
        else 0
    )

    out["gex"] = (
        sign *
        out["gamma_abs"] *
        out["oi"] *
        cfg.contract_multiplier *
        (spot ** 2) *
        0.01
    )

    out["abs_gex"] = (
        out["gex"].abs()
    )

    return out, spot


def summarize_gamma(df, spot):
    by = (
        df.groupby(
            "strike",
            as_index=False
        )
        .agg(
            net_gex=("gex", "sum"),
            abs_gex=("abs_gex", "sum")
        )
        .sort_values("strike")
    )

    calls = (
        df[
            df["side"]
            .astype(str)
            .str.lower()
            .str.startswith("c")
        ]
        .groupby(
            "strike",
            as_index=False
        )
        .agg(
            call_gex=("gex", "sum")
        )
    )

    puts = (
        df[
            df["side"]
            .astype(str)
            .str.lower()
            .str.startswith("p")
        ]
        .groupby(
            "strike",
            as_index=False
        )
        .agg(
            put_gex=("gex", "sum")
        )
    )

    by = by.merge(
        calls,
        on="strike",
        how="left"
    )

    by = by.merge(
        puts,
        on="strike",
        how="left"
    )

    by["call_gex"] = (
        by["call_gex"].fillna(0)
    )

    by["put_gex"] = (
        by["put_gex"].fillna(0)
    )

    call_wall = float(
        by.loc[
            by["call_gex"].idxmax(),
            "strike"
        ]
    )

    put_wall = float(
        by.loc[
            by["put_gex"].idxmin(),
            "strike"
        ]
    )

    temp = by.copy()

    temp["cum_gex"] = (
        temp["net_gex"].cumsum()
    )

    gamma_flip = math.nan

    vals = temp[
        ["strike", "cum_gex"]
    ].values

    for i in range(
        1,
        len(vals)
    ):
        s0, g0 = vals[i - 1]
        s1, g1 = vals[i]

        if g0 == 0:
            gamma_flip = float(s0)
            break

        if g0 * g1 < 0:
            gamma_flip = float(
                s0 +
                (0 - g0) *
                (s1 - s0) /
                (g1 - g0)
            )
            break

    total = float(
        by["net_gex"].sum()
    )

    regime = (
        "POSITIVE GAMMA"
        if total > 0
        else "NEGATIVE GAMMA"
    )

    return {
        "spot": spot,
        "net_gex": total,
        "regime": regime,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_flip": gamma_flip,
        "by_strike": by
    }
