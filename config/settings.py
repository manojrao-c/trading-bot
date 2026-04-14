"""
config/settings.py — Central configuration loader
Reads all values from .env — never hardcode secrets here.
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Config:
    # ── Alpaca (US Stocks — Paper Trading) ───────────────────
    ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY",    "")
    ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_BASE_URL   = os.getenv(
        "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
    )

    # ── Telegram ──────────────────────────────────────────────
    TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID",   "")

    # ── Capital ───────────────────────────────────────────────
    PAPER_CAPITAL_USD  = float(os.getenv("PAPER_CAPITAL_USD",   10_000))
    PAPER_CAPITAL_INR  = float(os.getenv("PAPER_CAPITAL_INR",  500_000))
    # .env uses PAPER_CAPITAL_CRYPTO — mapped to PAPER_CAPITAL_USDT
    # so broker/manager code that references cfg.PAPER_CAPITAL_USDT works.
    PAPER_CAPITAL_USDT = float(os.getenv("PAPER_CAPITAL_CRYPTO", 10_000))

    # ── Risk controls ─────────────────────────────────────────
    RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 1.5))
    MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY",   10))
    MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT",  3.0))

    # ── Watchlists ────────────────────────────────────────────
    US_WATCHLIST     = os.getenv(
        "US_WATCHLIST", "AAPL,MSFT,GOOGL,TSLA,NVDA"
    ).split(",")
    NSE_WATCHLIST    = os.getenv(
        "NSE_WATCHLIST", "RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK"
    ).split(",")
    CRYPTO_WATCHLIST = os.getenv(
        "CRYPTO_WATCHLIST", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"
    ).split(",")

    # ── Base strategy parameters (US + NSE) ───────────────────
    # Classic 9/21/50 EMA stack — well-proven on hourly charts
    EMA_FAST  = int(os.getenv("EMA_FAST",  9))
    EMA_SLOW  = int(os.getenv("EMA_SLOW",  21))
    EMA_TREND = int(os.getenv("EMA_TREND", 50))

    RSI_PERIOD     = int(os.getenv("RSI_PERIOD",     14))
    RSI_OVERSOLD   = int(os.getenv("RSI_OVERSOLD",   30))
    RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", 70))

    # stop = ATR_MULTIPLIER x ATR
    # target = ATR_MULTIPLIER x ATR x MIN_RR_RATIO
    # e.g. 2.0 x ATR stop, 4.0 x ATR target (1:2 RR)
    ATR_MULTIPLIER = float(os.getenv("ATR_MULTIPLIER", 2.0))
    MIN_RR_RATIO   = float(os.getenv("MIN_RR_RATIO",   2.0))

    # ── Crypto-specific overrides ─────────────────────────────
    # Wider ATR for higher crypto volatility.
    # Tighter RSI bands (65/35) to avoid entering during extreme moves.
    CRYPTO_ATR_MULTIPLIER = float(os.getenv("CRYPTO_ATR_MULTIPLIER", 2.5))
    CRYPTO_RSI_OVERSOLD   = int(os.getenv("CRYPTO_RSI_OVERSOLD",     35))
    CRYPTO_RSI_OVERBOUGHT = int(os.getenv("CRYPTO_RSI_OVERBOUGHT",   65))

    # ── Binance (Crypto — Testnet) ────────────────────────────
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY",    "")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
    ENABLE_CRYPTO = os.getenv("ENABLE_CRYPTO", False)

    # ── Startup validation ────────────────────────────────────
    def validate(self):
        """
        Call cfg.validate() at the top of main.py.
        Raises a clear error immediately on startup if required keys are missing.
        """
        missing = []
        if not self.ALPACA_API_KEY:
            missing.append("ALPACA_API_KEY")
        if not self.ALPACA_SECRET_KEY:
            missing.append("ALPACA_SECRET_KEY")
        if not self.TELEGRAM_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.TELEGRAM_CHAT_ID:
            missing.append("TELEGRAM_CHAT_ID")

        if missing:
            raise EnvironmentError(
                "Missing required .env variables: " + ", ".join(missing) + "\n"
                "Copy config.env.template to .env and fill in your keys."
            )


cfg = Config()