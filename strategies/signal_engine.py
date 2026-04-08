"""
strategies/signal_engine.py — Multi-indicator Signal Engine
Strategy: EMA crossover + RSI filter + ATR-based stops
Timeframe: Works on any OHLCV DataFrame
"""
import pandas as pd
import numpy as np
from config.settings import cfg


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to OHLCV dataframe."""
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # ── EMAs ─────────────────────────────────────────────────
    df["ema_fast"]  = c.ewm(span=cfg.EMA_FAST,  adjust=False).mean()
    df["ema_slow"]  = c.ewm(span=cfg.EMA_SLOW,  adjust=False).mean()
    df["ema_trend"] = c.ewm(span=cfg.EMA_TREND, adjust=False).mean()

    # ── RSI ───────────────────────────────────────────────────
    delta  = c.diff()
    gain   = delta.clip(lower=0).ewm(com=cfg.RSI_PERIOD - 1, adjust=False).mean()
    loss   = (-delta.clip(upper=0)).ewm(com=cfg.RSI_PERIOD - 1, adjust=False).mean()
    rs     = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── ATR (for stop-loss placement) ────────────────────────
    hl  = h - l
    hpc = (h - c.shift()).abs()
    lpc = (l - c.shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=14, adjust=False).mean()

    # ── VWAP (intraday reference) ─────────────────────────────
    if "volume" in df.columns:
        typical = (h + l + c) / 3
        df["vwap"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum()

    # ── Volume spike ─────────────────────────────────────────
    if "volume" in df.columns:
        df["vol_avg"]   = df["volume"].rolling(20).mean()
        df["vol_spike"] = df["volume"] > df["vol_avg"] * 1.5

    return df


def generate_signal(df: pd.DataFrame) -> dict:
    """
    Analyse the latest candle and return a trading signal.

    Returns:
        {
          "signal":     "BUY" | "SELL" | "HOLD",
          "strength":   1-3 (confluence score),
          "reasons":    [list of triggered conditions],
          "entry":      price,
          "stop_loss":  price,
          "take_profit":price,
          "atr":        value,
          "rsi":        value,
        }
    """
    df = compute_indicators(df.copy())

    if len(df) < cfg.EMA_TREND + 5:
        return {"signal": "HOLD", "strength": 0, "reasons": ["Insufficient data"]}

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    reasons   = []
    buy_score  = 0
    sell_score = 0

    # ── EMA crossover ────────────────────────────────────────
    ema_cross_up   = prev["ema_fast"] <= prev["ema_slow"] and latest["ema_fast"] > latest["ema_slow"]
    ema_cross_down = prev["ema_fast"] >= prev["ema_slow"] and latest["ema_fast"] < latest["ema_slow"]

    if ema_cross_up:
        buy_score += 1
        reasons.append("EMA fast crossed above slow (bullish)")
    if ema_cross_down:
        sell_score += 1
        reasons.append("EMA fast crossed below slow (bearish)")

    # ── Trend filter: price above/below EMA 50 ────────────────
    above_trend = latest["close"] > latest["ema_trend"]
    below_trend = latest["close"] < latest["ema_trend"]

    if above_trend and buy_score > 0:
        buy_score += 1
        reasons.append("Price above EMA-50 (uptrend confirmed)")
    if below_trend and sell_score > 0:
        sell_score += 1
        reasons.append("Price below EMA-50 (downtrend confirmed)")

    # ── RSI filter ────────────────────────────────────────────
    rsi = latest["rsi"]
    if rsi < cfg.RSI_OVERBOUGHT and buy_score > 0:
        buy_score += 1
        reasons.append(f"RSI {rsi:.1f} — not overbought, room to run")
    if rsi > cfg.RSI_OVERSOLD and sell_score > 0:
        sell_score += 1
        reasons.append(f"RSI {rsi:.1f} — not oversold, room to fall")

    # ── Volume confirmation ───────────────────────────────────
    if "vol_spike" in latest and latest["vol_spike"]:
        if buy_score > 0:
            buy_score += 1
            reasons.append("Volume spike confirms move")
        if sell_score > 0:
            sell_score += 1
            reasons.append("Volume spike confirms move")

    # ── Determine signal ──────────────────────────────────────
    atr   = latest["atr"]
    price = latest["close"]

    if buy_score >= 2:
        stop_loss   = round(price - (atr * cfg.ATR_MULTIPLIER), 4)
        take_profit = round(price + (atr * cfg.ATR_MULTIPLIER * cfg.MIN_RR_RATIO), 4)
        return {
            "signal":      "BUY",
            "strength":    min(buy_score, 3),
            "reasons":     reasons,
            "entry":       round(price, 4),
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "atr":         round(atr, 4),
            "rsi":         round(rsi, 1),
        }
    elif sell_score >= 2:
        stop_loss   = round(price + (atr * cfg.ATR_MULTIPLIER), 4)
        take_profit = round(price - (atr * cfg.ATR_MULTIPLIER * cfg.MIN_RR_RATIO), 4)
        return {
            "signal":      "SELL",
            "strength":    min(sell_score, 3),
            "reasons":     reasons,
            "entry":       round(price, 4),
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "atr":         round(atr, 4),
            "rsi":         round(rsi, 1),
        }
    else:
        return {
            "signal":   "HOLD",
            "strength": 0,
            "reasons":  reasons or ["No confluence — staying out"],
            "rsi":      round(rsi, 1) if not pd.isna(rsi) else None,
        }
