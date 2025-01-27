from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import sqlite3
import pandas as pd
from datetime import datetime
import pyupbit
import ta
from ta.utils import dropna
import asyncio
from typing import List
import os
from dotenv import load_dotenv
import logging
import json

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Trading Bot API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
def get_db():
    conn = sqlite3.connect('bitcoin_trades.db')
    return conn

# Data models
class TradingDecision(BaseModel):
    decision: str
    percentage: int
    reason: str

class MarketData(BaseModel):
    current_price: float
    daily_change: float
    volume: float
    timestamp: str

# Global variables
trading_task = None
is_trading_active = False

# Trading bot logic
async def trading_bot():
    while is_trading_active:
        try:
            logger.info("Executing trading cycle...")
            await execute_trading_cycle()
            await asyncio.sleep(14400)  # 4 hours interval
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error

async def execute_trading_cycle():
    try:
        # Upbit 객체 초기화
        upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))

        # 잔고 조회
        balances = upbit.get_balances()
        krw_balance = float([x for x in balances if x['currency'] == 'KRW'][0]['balance'])
        btc_balance = float([x for x in balances if x['currency'] == 'BTC'][0]['balance'])
        
        # 현재 비트코인 가격 조회
        current_price = pyupbit.get_current_price("KRW-BTC")
        if current_price is None:
            raise ValueError("현재 가격 데이터를 가져올 수 없습니다.")

        # 매수 금액: KRW 잔고의 20%
        buy_amount = krw_balance * 0.2

        # 매도 수량: BTC 잔고의 20%
        sell_quantity = btc_balance * 0.2

        # 매수 로직
        if buy_amount >= 5000:  # 업비트 최소 매수 금액이 5000원
            buy_response = upbit.buy_market_order("KRW-BTC", buy_amount)
            logger.info(f"매수 실행: {buy_response}")
        else:
            logger.info("매수 금액이 최소 금액(5000원)보다 작아서 매수하지 않았습니다.")

        # 매도 로직
        if sell_quantity * current_price >= 5000:  # 매도 금액이 최소 5000원 이상이어야 함
            sell_response = upbit.sell_market_order("KRW-BTC", sell_quantity)
            logger.info(f"매도 실행: {sell_response}")
        else:
            logger.info("매도 금액이 최소 금액(5000원)보다 작아서 매도하지 않았습니다.")
    except Exception as e:
        logger.error(f"거래 실행 중 에러 발생: {e}")

@app.get("/api/account-balances")
async def get_account_balances():
    try:
        # Upbit 객체 초기화
        upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))

        # 잔고 조회
        balances = upbit.get_balances()
        
        # KRW 및 BTC 잔고 추출
        krw_balance = next((float(x['balance']) for x in balances if x['currency'] == 'KRW'), 0.0)
        btc_balance = next((float(x['balance']) for x in balances if x['currency'] == 'BTC'), 0.0)

        return {"KRW": krw_balance, "BTC": btc_balance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch account balances: {e}")

# API endpoints
@app.get("/api/market-data")
async def get_market_data():
    try:
        # 현재 가격 가져오기
        current_price = pyupbit.get_current_price("KRW-BTC")
        if not current_price:
            raise ValueError("현재 가격 데이터를 가져오지 못했습니다.")
        
        # 일간 변동률 및 거래량 데이터를 가져오기 위해 OHLCV 사용
        ohlcv = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=2)
        if ohlcv is None or len(ohlcv) < 2:
            raise ValueError("OHLCV 데이터를 가져오지 못했습니다.")

        # 전날 종가와 현재 가격으로 변동률 계산
        prev_close = ohlcv.iloc[-2]["close"]
        daily_change = ((current_price - prev_close) / prev_close) * 100

        # 24시간 거래량
        volume = ohlcv.iloc[-1]["volume"]

        return MarketData(
            current_price=current_price,
            daily_change=daily_change,
            volume=volume,
            timestamp=datetime.now().isoformat()
        )
    except ValueError as ve:
        logger.error(f"ValueError: {ve}")
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="예상치 못한 에러가 발생했습니다.")

@app.get("/api/trading-history")
async def execute_trading_cycle():
    try:
        # Upbit 객체 초기화
        upbit = pyupbit.Upbit(os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY"))

        # 잔고 조회
        balances = upbit.get_balances()

        # KRW 잔고 조회 (없으면 0으로 설정)
        krw_balance = next((float(x['balance']) for x in balances if x['currency'] == 'KRW'), 0.0)

        # BTC 잔고 조회 (없으면 0으로 설정)
        btc_balance = next((float(x['balance']) for x in balances if x['currency'] == 'BTC'), 0.0)

        # 현재 비트코인 가격 조회
        current_price = pyupbit.get_current_price("KRW-BTC")
        if current_price is None:
            raise ValueError("현재 가격 데이터를 가져올 수 없습니다.")

        # 매수 금액: KRW 잔고의 20%
        buy_amount = krw_balance * 0.2

        # 매도 수량: BTC 잔고의 20%
        sell_quantity = btc_balance * 0.2

        # 매수 로직
        if buy_amount >= 5000:  # 업비트 최소 매수 금액이 5000원
            buy_response = upbit.buy_market_order("KRW-BTC", buy_amount)
            logger.info(f"매수 실행: {buy_response}")
        else:
            logger.info("매수 금액이 최소 금액(5000원)보다 작아서 매수하지 않았습니다.")

        # 매도 로직
        if sell_quantity * current_price >= 5000:  # 매도 금액이 최소 5000원 이상이어야 함
            sell_response = upbit.sell_market_order("KRW-BTC", sell_quantity)
            logger.info(f"매도 실행: {sell_response}")
        else:
            logger.info("매도 금액이 최소 금액(5000원)보다 작아서 매도하지 않았습니다.")
    except Exception as e:
        logger.error(f"거래 실행 중 에러 발생: {e}")

@app.get("/api/chart-data")
async def get_chart_data(timeframe: str = "1h", limit: int = 168):
    try:
        interval_map = {"1h": "minute60", "4h": "minute240", "1d": "day"}
        if timeframe not in interval_map:
            raise ValueError("Invalid timeframe. Use '1h', '4h', or '1d'.")

        df = pyupbit.get_ohlcv("KRW-BTC", interval=interval_map[timeframe], count=limit)
        df = dropna(df)

        # Add technical indicators
        df['RSI'] = ta.momentum.RSIIndicator(df['close']).rsi()
        bb = ta.volatility.BollingerBands(df['close'])
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_lower'] = bb.bollinger_lband()
        df['BB_middle'] = bb.bollinger_mavg()

        macd = ta.trend.MACD(df['close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()

        return json.loads(df.to_json(orient='records', date_format='iso'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chart data: {e}")

@app.post("/api/toggle-trading")
async def toggle_trading():
    global is_trading_active, trading_task

    is_trading_active = not is_trading_active

    if is_trading_active:
        if trading_task is None:
            trading_task = asyncio.create_task(trading_bot())
    else:
        if trading_task:
            trading_task.cancel()
            trading_task = None

    return {"status": "active" if is_trading_active else "inactive"}

@app.on_event("startup")
async def startup_event():
    # Initialize the database on server startup
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 timestamp TEXT,
                 decision TEXT,
                 percentage INTEGER,
                 reason TEXT,
                 btc_balance REAL,
                 krw_balance REAL,
                 btc_avg_buy_price REAL,
                 btc_krw_price REAL)''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
