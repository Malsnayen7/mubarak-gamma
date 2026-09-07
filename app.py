import os
import json
import requests
import streamlit as st

st.set_page_config(
    page_title="Mubarak Gamma Diagnostic",
    layout="wide"
)

st.title("Mubarak Gamma — API Diagnostic")
st.caption("اختبار اتصال MarketData.app قبل تشغيل محرك Gamma.")

token = st.sidebar.text_input(
    "MarketData API Token",
    value=os.getenv("MARKETDATA_TOKEN", ""),
    type="password"
)

symbol = st.sidebar.text_input(
    "Symbol",
    value="SPY"
).strip().upper()

run = st.sidebar.button(
    "Test MarketData API",
    type="primary"
)

def call_api(url, token):
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    return response

if run:

    if not token:
        st.error("Please enter your MarketData API Token.")
        st.stop()

    st.subheader("Step 1 — Option Expirations")

    exp_url = (
        f"https://api.marketdata.app/v1/options/expirations/"
        f"{symbol}/"
    )

    try:
        exp_response = call_api(exp_url, token)

        st.write(
            "HTTP Status:",
            exp_response.status_code
        )

        try:
            exp_data = exp_response.json()
            st.json(exp_data)
        except Exception:
            st.code(exp_response.text)

    except Exception as e:
        st.error(
            f"Expiration request failed: {e}"
        )
        st.stop()

    st.divider()

    st.subheader("Step 2 — Option Chain")

    chain_url = (
        f"https://api.marketdata.app/v1/options/chain/"
        f"{symbol}/"
    )

    try:
        chain_response = call_api(
            chain_url,
            token
        )

        st.write(
            "HTTP Status:",
            chain_response.status_code
        )

        try:
            chain_data = chain_response.json()

            if isinstance(chain_data, dict):

                status = chain_data.get(
                    "s",
                    "unknown"
                )

                st.write(
                    "API Status:",
                    status
                )

                if "errmsg" in chain_data:
                    st.error(
                        chain_data["errmsg"]
                    )

                symbols = chain_data.get(
                    "symbol",
                    []
                )

                if isinstance(symbols, list):
                    st.metric(
                        "Option contracts returned",
                        len(symbols)
                    )

                st.json(chain_data)

            else:
                st.json(chain_data)

        except Exception:
            st.code(
                chain_response.text
            )

    except Exception as e:
        st.error(
            f"Option chain request failed: {e}"
        )

    st.divider()

    st.info(
        "Do not send your API Token. "
        "Send only a screenshot of the diagnostic results."
    )

else:

    st.info(
        "Enter your token, keep SPY as the symbol, "
        "then press Test MarketData API."
    )
