"""
strategies/signal_engine.py — Multi-indicator Signal Engine
Strategy: EMA crossover + RSI filter + ATR-based stops
Timeframe: Works on any OHLCV DataFrame (hourly recommended)
"""
import pandas as pd
import numpy as np
from config.settings import cfg


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to OHLCV dataframe."""
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # EMAs
    df["ema_fast"]  = c.ewm(span=cfg.EMA_FAST,  adjust=False).mean()
    df["ema_slow"]  = c.ewm(span=cfg.EMA_SLOW,  adjust=False).mean()
    df["ema_trend"] = c.ewm(span=cfg.EMA_TREND, adjust=False).mean()

    # RSI
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(com=cfg.RSI_PERIOD - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=cfg.RSI_PERIOD - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR (14-period, for stop placement)
    hl  = h - l
    hpc = (h - c.shift()).abs()
    lpc = (l - c.shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=14, adjust=False).mean()

    # VWAP (intraday reference)
    if "volume" in df.columns:
        typical   = (h + l + c) / 3
        df["vwap"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum()

    # Volume spike (> 1.5x 20-bar average)
    if "volume" in df.columns:
        df["vol_avg"]   = df["volume"].rolling(20).mean()
        df["vol_spike"] = df["volume"] > df["vol_avg"] * 1.5

    return df


def generate_signal(df: pd.DataFrame, market: str = "US") -> dict:
    """
    Analyse the latest candle and return a trading signal.

    Parameters
    ----------
    df     : OHLCV DataFrame (at least EMA_TREND + 5 rows)
    market : "US" | "NSE" | "CRYPTO"
             Selects the correct ATR multiplier and RSI bands from cfg.
             - US / NSE  : cfg.ATR_MULTIPLIER, cfg.RSI_OVERSOLD/OVERBOUGHT
             - CRYPTO    : cfg.CRYPTO_ATR_MULTIPLIER,
                           cfg.CRYPTO_RSI_OVERSOLD/OVERBOUGHT

    Returns
    -------
    dict with keys:
        signal      : "BUY" | "SELL" | "HOLD"
        strength    : int 1-3  (confluence score)
        reasons     : list[str]
        entry       : float
        stop_loss   : float | None
        take_profit : float | None
        atr         : float
        rsi         : float | None
    """
    # ── Pick correct params for this market ──────────────────
    if market == "CRYPTO":
        atr_mult   = cfg.CRYPTO_ATR_MULTIPLIER
        rsi_ob     = cfg.CRYPTO_RSI_OVERBOUGHT   # 65
        rsi_os     = cfg.CRYPTO_RSI_OVERSOLD     # 35
    else:                                         # US or NSE
        atr_mult   = cfg.ATR_MULTIPLIER
        rsi_ob     = cfg.RSI_OVERBOUGHT           # 70
        rsi_os     = cfg.RSI_OVERSOLD             # 30

    df = compute_indicators(df.copy())

    if len(df) < cfg.EMA_TREND + 5:
        return {"signal": "HOLD", "strength": 0,
                "reasons": ["Insufficient data"],
                "entry": None, "stop_loss": None,
                "take_profit": None, "atr": None, "rsi": None}

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    reasons    = []
    buy_score  = 0
    sell_score = 0

    # ── EMA crossover ─────────────────────────────────────────
    ema_cross_up   = (prev["ema_fast"] <= prev["ema_slow"]
                      and latest["ema_fast"] > latest["ema_slow"])
    ema_cross_down = (prev["ema_fast"] >= prev["ema_slow"]
                      and latest["ema_fast"] < latest["ema_slow"])

    if ema_cross_up:
        buy_score += 1
        reasons.append("EMA fast crossed above slow (bullish)")
    if ema_cross_down:
        sell_score += 1
        reasons.append("EMA fast crossed below slow (bearish)")

    # ── Trend filter: price vs EMA-50 ─────────────────────────
    above_trend = latest["close"] > latest["ema_trend"]
    below_trend = latest["close"] < latest["ema_trend"]

    if above_trend and buy_score > 0:
        buy_score += 1
        reasons.append("Price above EMA-50 (uptrend confirmed)")
    if below_trend and sell_score > 0:
        sell_score += 1
        reasons.append("Price below EMA-50 (downtrend confirmed)")

    # ── RSI filter (uses market-specific bands) ───────────────
    rsi = latest["rsi"]
    if rsi < rsi_ob and buy_score > 0:
        buy_score += 1
        reasons.append(f"RSI {rsi:.1f} below {rsi_ob} — room to run")
    if rsi > rsi_os and sell_score > 0:
        sell_score += 1
        reasons.append(f"RSI {rsi:.1f} above {rsi_os} — room to fall")

    # ── Volume confirmation ────────────────────────────────────
    if "vol_spike" in latest and latest["vol_spike"]:
        if buy_score > 0:
            buy_score  += 1
            reasons.append("Volume spike confirms move")
        if sell_score > 0:
            sell_score += 1
            reasons.append("Volume spike confirms move")

    # ── Build signal ──────────────────────────────────────────
    atr   = latest["atr"]
    price = latest["close"]

    if buy_score >= 2:
        stop_loss   = round(price - (atr * atr_mult), 4)
        take_profit = round(price + (atr * atr_mult * cfg.MIN_RR_RATIO), 4)
        return {
            "signal":      "BUY",
            "strength":    min(buy_score, 3),
            "reasons":     reasons,
            "entry":       round(price, 4),
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "atr":         round(float(atr), 4),
            "rsi":         round(float(rsi), 1),
        }

    if sell_score >= 2:
        stop_loss   = round(price + (atr * atr_mult), 4)
        take_profit = round(price - (atr * atr_mult * cfg.MIN_RR_RATIO), 4)
        return {
            "signal":      "SELL",
            "strength":    min(sell_score, 3),
            "reasons":     reasons,
            "entry":       round(price, 4),
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "atr":         round(float(atr), 4),
            "rsi":         round(float(rsi), 1),
        }

    return {
        "signal":      "HOLD",
        "strength":    0,
        "reasons":     reasons or ["No confluence — staying out"],
        "entry":       round(float(price), 4),
        "stop_loss":   None,
        "take_profit": None,
        "atr":         round(float(atr), 4),
        "rsi":         round(float(rsi), 1) if not pd.isna(rsi) else None,
    }
