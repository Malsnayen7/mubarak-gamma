import os
import math
import streamlit as st
from gamma_engine import GammaConfig, fetch_option_chain, normalize_chain, summarize_gamma

st.set_page_config(page_title="Mubarak Gamma V1", layout="wide")
st.title("Mubarak Gamma V1 — Daily / Monthly Options")
st.caption("Gamma dashboard for monthly/swing option decisions.")

token = st.sidebar.text_input("MarketData API Token", value=os.getenv("MARKETDATA_TOKEN",""), type="password")
symbol = st.sidebar.text_input("Symbol", value="SPY").strip().upper()
min_dte = st.sidebar.number_input("Minimum DTE", 1, 365, 20)
max_dte = st.sidebar.number_input("Maximum DTE", 2, 730, 60)
strike_pct = st.sidebar.slider("Strike range around spot", 5, 40, 15) / 100.0
run = st.sidebar.button("Refresh Gamma", type="primary")

def money(x):
    if x is None or (isinstance(x,float) and math.isnan(x)): return "—"
    a=abs(x); sign="-" if x<0 else ""
    if a>=1e9: return f"{sign}${a/1e9:.2f}B"
    if a>=1e6: return f"{sign}${a/1e6:.2f}M"
    if a>=1e3: return f"{sign}${a/1e3:.1f}K"
    return f"{sign}${a:.0f}"

if run:
    if not token:
        st.error("Enter your MarketData API token first.")
        st.stop()
    try:
        raw = fetch_option_chain(symbol, token)
        chain, spot = normalize_chain(raw, GammaConfig(int(min_dte), int(max_dte), float(strike_pct)))
        s = summarize_gamma(chain, spot)
    except Exception as e:
        st.error(str(e)); st.stop()

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Spot", f"{s['spot']:.2f}")
    c2.metric("Net GEX", money(s["net_gex"]))
    c3.metric("Call Wall", f"{s['call_wall']:.2f}" if math.isfinite(s["call_wall"]) else "—")
    c4.metric("Put Wall", f"{s['put_wall']:.2f}" if math.isfinite(s["put_wall"]) else "—")
    c5.metric("Gamma Flip", f"{s['gamma_flip']:.2f}" if math.isfinite(s["gamma_flip"]) else "—")
    st.subheader(f"Regime: {s['regime']}")
    st.dataframe(s["by_strike"], hide_index=True, use_container_width=True)
else:
    st.info("Enter your API token and press Refresh Gamma.")
