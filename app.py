import os
import math
import streamlit as st

from gamma_engine import GammaConfig, fetch_option_chain, normalize_chain, summarize_gamma

st.set_page_config(page_title="Mubarak Gamma V1", layout="wide")
st.title("Mubarak Gamma V1 — Daily / Monthly Options")
st.caption("Gamma dashboard for monthly/swing option decisions.")

secret_token = ""
try:
    secret_token = st.secrets.get("MARKETDATA_TOKEN", "")
except Exception:
    secret_token = ""

default_token = secret_token or os.getenv("MARKETDATA_TOKEN", "")

token = st.sidebar.text_input("MarketData API Token", value=default_token, type="password")
symbol = st.sidebar.text_input("Symbol", value="SPY").strip().upper()
min_dte = st.sidebar.number_input("Minimum DTE", min_value=1, max_value=365, value=20, step=1)
max_dte = st.sidebar.number_input("Maximum DTE", min_value=1, max_value=365, value=60, step=1)
strike_pct = st.sidebar.slider("Strike range around spot (%)", min_value=5, max_value=40, value=15, step=1)
run = st.sidebar.button("Refresh Gamma", type="primary")

def money(x):
    if x is None:
        return "N/A"
    try:
        if math.isnan(float(x)):
            return "N/A"
    except Exception:
        pass
    x = float(x)
    a = abs(x)
    sign = "-" if x < 0 else ""
    if a >= 1e9:
        return f"{sign}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:.2f}M"
    if a >= 1e3:
        return f"{sign}${a/1e3:.1f}K"
    return f"{sign}${a:.0f}"

if run:
    if not token:
        st.error("Enter your MarketData API token.")
        st.stop()

    if min_dte > max_dte:
        st.error("Minimum DTE cannot be greater than Maximum DTE.")
        st.stop()

    cfg = GammaConfig(
        min_dte=int(min_dte),
        max_dte=int(max_dte),
        strike_pct=float(strike_pct) / 100.0,
    )

    try:
        raw = fetch_option_chain(symbol, token)
        chain, spot = normalize_chain(raw, cfg)
        s = summarize_gamma(chain, spot)
    except Exception as e:
        st.error(str(e))
        st.stop()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Spot", f"${s['spot']:.2f}")
    c2.metric("Net GEX", money(s["net_gex"]))
    c3.metric("Call Wall", "N/A" if math.isnan(s["call_wall"]) else f"${s['call_wall']:.2f}")
    c4.metric("Put Wall", "N/A" if math.isnan(s["put_wall"]) else f"${s['put_wall']:.2f}")
    c5.metric("Gamma Flip", "N/A" if math.isnan(s["gamma_flip"]) else f"${s['gamma_flip']:.2f}")

    st.subheader(f"Regime: {s['regime']}")
    if s["regime"] == "POSITIVE GAMMA":
        st.success("Positive Gamma regime: price action may be more stable and mean-reverting around major gamma levels.")
    else:
        st.warning("Negative Gamma regime: price action may be more volatile and directional.")

    st.subheader("Gamma by Strike")
    st.bar_chart(s["by_strike"].set_index("strike")[["net_gex"]])

    st.subheader("Strike Table")
    st.dataframe(s["by_strike"], use_container_width=True, hide_index=True)

    st.subheader("Contracts Used")
    st.dataframe(
        chain[["optionSymbol", "expiration_dt", "dte", "side", "strike", "openInterest", "gamma", "gex"]],
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        f"Contracts used: {len(chain):,} | DTE: {int(min_dte)}–{int(max_dte)} | Strike range: ±{int(strike_pct)}%"
    )
else:
    st.info("Enter your API token, choose a symbol, then press Refresh Gamma.")
