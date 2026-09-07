import os
import math
import streamlit as st

from gamma_engine import (
    GammaConfig,
    fetch_option_chain,
    normalize_chain,
    summarize_gamma
)

st.set_page_config(
    page_title="Mubarak Gamma V1",
    layout="wide"
)

st.title("Mubarak Gamma V1 — Daily / Monthly Options")
st.caption("Gamma dashboard for monthly/swing option decisions.")

token = st.sidebar.text_input(
    "MarketData API Token",
    value=os.getenv("MARKETDATA_TOKEN", ""),
    type="password"
)

symbol = st.sidebar.text_input(
    "Symbol",
    value="SPY"
).strip().upper()

min_dte = st.sidebar.number_input(
    "Minimum DTE",
    min_value=1,
    max_value=365,
    value=20
)

max_dte = st.sidebar.number_input(
    "Maximum DTE",
    min_value=1,
    max_value=365,
    value=60
)

strike_pct = st.sidebar.slider(
    "Strike range around spot",
    min_value=5,
    max_value=40,
    value=15
)

run = st.sidebar.button(
    "Refresh Gamma",
    type="primary"
)


def money(x):
    if x is None:
        return "N/A"

    try:
        if math.isnan(x):
            return "N/A"
    except Exception:
        pass

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

    cfg = GammaConfig(
        min_dte=int(min_dte),
        max_dte=int(max_dte),
        strike_pct=float(strike_pct) / 100.0
    )

    try:
        raw = fetch_option_chain(
            symbol,
            token
        )

        chain, spot = normalize_chain(
            raw,
            cfg
        )

        s = summarize_gamma(
            chain,
            spot
        )

    except Exception as e:
        st.error(str(e))
        st.stop()

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "Spot",
        f"${s['spot']:.2f}"
    )

    c2.metric(
        "Net GEX",
        money(s["net_gex"])
    )

    c3.metric(
        "Call Wall",
        f"${s['call_wall']:.2f}"
    )

    c4.metric(
        "Put Wall",
        f"${s['put_wall']:.2f}"
    )

    if math.isnan(s["gamma_flip"]):
        flip_text = "N/A"
    else:
        flip_text = f"${s['gamma_flip']:.2f}"

    c5.metric(
        "Gamma Flip",
        flip_text
    )

    st.subheader(
        f"Regime: {s['regime']}"
    )

    if s["regime"] == "POSITIVE GAMMA":
        st.success(
            "Positive Gamma regime: price action may be more stable and mean-reverting around major gamma levels."
        )
    else:
        st.warning(
            "Negative Gamma regime: price action may be more volatile and directional."
        )

    st.subheader("Gamma by Strike")

    chart_df = (
        s["by_strike"]
        .set_index("strike")
        [["net_gex"]]
    )

    st.bar_chart(chart_df)

    st.subheader("Strike Table")

    st.dataframe(
        s["by_strike"],
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Contracts Used")

    st.dataframe(
        chain[
            [
                "optionSymbol",
                "expiration_dt",
                "side",
                "strike",
                "openInterest",
                "gamma",
                "gex"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Enter your API token, choose a symbol, then press Refresh Gamma."
    )
