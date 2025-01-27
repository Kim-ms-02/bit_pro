import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

# API 설정
API_URL = "http://localhost:8000/api"

# 페이지 설정
st.set_page_config(
    page_title="Bitcoin Trading 자동 프로그램",
    page_icon="📈",
    layout="wide"
)

# 스타일 설정
st.markdown("""
    <style>
    .big-font {
        font-size:24px !important;
        font-weight: bold;
    }
    .profit {
        color: #0ECB81;
        font-weight: bold;
    }
    .loss {
        color: #FF6B6B;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60)
def get_market_data():
    response = requests.get(f"{API_URL}/market-data")
    return response.json()

@st.cache_data(ttl=60)
def get_trading_history(days=7):
    response = requests.get(f"{API_URL}/trading-history", params={"days": days})
    return response.json()

@st.cache_data(ttl=60)
def get_account_balances():
    response = requests.get(f"{API_URL}/account-balances")
    return response.json()

@st.cache_data(ttl=300)
def get_hourly_data():
    response = requests.get(f"{API_URL}/chart-data", params={"timeframe": "1h", "limit": 24})
    data = response.json()
    df = pd.DataFrame(data)
    df.reset_index(inplace=True)
    df.rename(columns={"index": "Timestamp"}, inplace=True)
    return df

def toggle_trading():
    response = requests.post(f"{API_URL}/toggle-trading")
    return response.json()

def main():
    st.title("Bitcoin 자동 매매 프로그램")

    # 트레이딩 봇 컨트롤
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("매수/매도 전환"):
            result = toggle_trading()
            st.success(f"매수/매도 전환 : {result['status']}")

    # 시장 데이터 표시
    try:
        market_data = get_market_data()
        
        with col2:
            st.metric(
                label="비트코인 원화 기준",
                value=f"₩{market_data['current_price']:,.0f}",
                delta=f"{market_data['daily_change']:.2f}%"
            )
        
        with col3:
            st.metric(
                label="24시간 이동범위",
                value=f"{market_data['volume']:,.2f} BTC"
            )
    except Exception as e:
        st.error(f"Failed to fetch market data: {str(e)}")

    # 잔고 표시
    st.subheader("지갑 잔고")
    try:
        balances = get_account_balances()
        if balances:
            krw_balance = balances.get("KRW", 0.0)
            btc_balance = balances.get("BTC", 0.0)
            st.metric(label="KRW 잔고", value=f"₩{krw_balance:,.0f}")
            st.metric(label="BTC 잔고", value=f"{btc_balance:.6f} BTC")
        else:
            st.info("No account balances available")
    except Exception as e:
        st.error(f"Failed to load account balances: {str(e)}")

    # 시간당 비트코인 데이터 표시
    st.subheader("시간당 비트코인 데이터")
    try:
        hourly_data = get_hourly_data()
        hourly_data = hourly_data[['Timestamp', 'open', 'high', 'low', 'close', 'volume']]
        hourly_data.columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
        st.dataframe(hourly_data, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load hourly data: {str(e)}")

    # 거래 내역 표시
    st.subheader("거래 내역")
    try:
        trading_history = pd.DataFrame(get_trading_history())
        if not trading_history.empty:
            st.dataframe(trading_history, use_container_width=True)
        else:
            st.info("거래 내역 없음")
    except Exception as e:
        st.error(f"Failed to load trading history: {str(e)}")

if __name__ == "__main__":
    main()