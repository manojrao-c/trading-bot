"""
config/settings.py — Central configuration loader
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Alpaca
    ALPACA_API_KEY     = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY  = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_BASE_URL    = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    # Telegram
    TELEGRAM_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

    # Capital
    PAPER_CAPITAL_USD  = float(os.getenv("PAPER_CAPITAL_USD", 10000))
    PAPER_CAPITAL_INR  = float(os.getenv("PAPER_CAPITAL_INR", 500000))
    RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 1.5))
    MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", 10))
    MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", 3.0))

    # Watchlists
    US_WATCHLIST  = os.getenv("US_WATCHLIST", "AAPL,MSFT,GOOGL,TSLA,NVDA").split(",")
    NSE_WATCHLIST = os.getenv("NSE_WATCHLIST", "RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK").split(",")

    # Strategy params
    EMA_FAST       = int(os.getenv("EMA_FAST", 9))
    EMA_SLOW       = int(os.getenv("EMA_SLOW", 21))
    EMA_TREND      = int(os.getenv("EMA_TREND", 50))
    RSI_PERIOD     = int(os.getenv("RSI_PERIOD", 14))
    RSI_OVERSOLD   = int(os.getenv("RSI_OVERSOLD", 30))
    RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", 70))
    ATR_MULTIPLIER = float(os.getenv("ATR_MULTIPLIER", 2.0))
    MIN_RR_RATIO   = float(os.getenv("MIN_RR_RATIO", 2.0))

    #Binance
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY: str = os.getenv("BINANCE_SECRET_KEY", "")
    CRYPTO_WATCHLIST: list = os.getenv("CRYPTO_WATCHLIST",
    "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT").split(",")
    PAPER_CAPITAL_CRYPTO: float = float(os.getenv("PAPER_CAPITAL_CRYPTO", 10000))
    PAPER_CAPITAL_USDT = 10000.0   # $10,000 testnet USDT

cfg = Config()
