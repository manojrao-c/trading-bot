"""
strategies/signal_engine.py — Multi-indicator Signal Engine
Strategy: EMA crossover (3-candle window) + RSI filter + ATR-based stops
Timeframe: Works on any OHLCV DataFrame (1h recommended)
Long-only agent — SELL = exit an existing long, not a short entry.
"""
import pandas as pd
import numpy as np
from config.settings import cfg

# How many recent candles to scan for a valid EMA crossover
EMA_CROSS_LOOKBACK = 3


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to OHLCV dataframe."""
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # ── EMAs ─────────────────────────────────────────────────
    df["ema_fast"]  = c.ewm(span=cfg.EMA_FAST,  adjust=False).mean()
    df["ema_slow"]  = c.ewm(span=cfg.EMA_SLOW,  adjust=False).mean()
    df["ema_trend"] = c.ewm(span=cfg.EMA_TREND, adjust=False).mean()

    # ── RSI (Wilder's smoothing via EWM) ─────────────────────
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(com=cfg.RSI_PERIOD - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=cfg.RSI_PERIOD - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── ATR (stop-loss placement) ─────────────────────────────
    hl  = h - l
    hpc = (h - c.shift()).abs()
    lpc = (l - c.shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=14, adjust=False).mean()

    # ── Volume spike ──────────────────────────────────────────
    if "volume" in df.columns:
        df["vol_avg"]   = df["volume"].rolling(20).mean()
        df["vol_spike"] = df["volume"] > df["vol_avg"] * 1.5

    return df


def _ema_crossed_up_recently(df: pd.DataFrame, lookback: int) -> bool:
    """
    Returns True if ema_fast crossed ABOVE ema_slow in the last `lookback` candles.
    Real traders don't demand the exact candle — a recent cross is still valid.
    """
    window = df.tail(lookback + 1)
    for i in range(len(window) - 1):
        prev   = window.iloc[i]
        latest = window.iloc[i + 1]
        if prev["ema_fast"] <= prev["ema_slow"] and latest["ema_fast"] > latest["ema_slow"]:
            return True
    return False


def _ema_crossed_down_recently(df: pd.DataFrame, lookback: int) -> bool:
    """
    Returns True if ema_fast crossed BELOW ema_slow in the last `lookback` candles.
    """
    window = df.tail(lookback + 1)
    for i in range(len(window) - 1):
        prev   = window.iloc[i]
        latest = window.iloc[i + 1]
        if prev["ema_fast"] >= prev["ema_slow"] and latest["ema_fast"] < latest["ema_slow"]:
            return True
    return False


def generate_signal(df: pd.DataFrame) -> dict:
    """
    Analyse the latest candle and return a trading signal.

    Long-only rules:
      BUY  — EMA bullish cross (within 3 candles) + price above EMA-50 + RSI not overbought
      SELL — EMA bearish cross (within 3 candles) + price below EMA-50 + RSI overbought OR collapsed
             (exits the existing long at market — no short entry)

    Returns dict with keys:
      signal, strength, reasons, entry, stop_loss, take_profit, atr, rsi
    """
    df = compute_indicators(df.copy())

    # Need enough candles for EMA_TREND to stabilise
    if len(df) < cfg.EMA_TREND + 5:
        return {
            "signal": "HOLD", "strength": 0,
            "reasons": ["Insufficient data"],
            "entry": None, "stop_loss": None, "take_profit": None, "atr": None, "rsi": None,
        }

    latest = df.iloc[-1]
    rsi    = latest["rsi"]
    atr    = latest["atr"]
    price  = latest["close"]

    reasons    = []
    buy_score  = 0
    sell_score = 0

    # ── Condition 1: EMA crossover (3-candle window) ──────────
    if _ema_crossed_up_recently(df, EMA_CROSS_LOOKBACK):
        buy_score += 1
        reasons.append(f"EMA fast crossed above slow (last {EMA_CROSS_LOOKBACK} candles)")

    if _ema_crossed_down_recently(df, EMA_CROSS_LOOKBACK):
        sell_score += 1
        reasons.append(f"EMA fast crossed below slow (last {EMA_CROSS_LOOKBACK} candles)")

    # ── Condition 2: Trend filter — price vs EMA-50 ───────────
    above_trend = latest["close"] > latest["ema_trend"]
    below_trend = latest["close"] < latest["ema_trend"]

    if above_trend and buy_score > 0:
        buy_score += 1
        reasons.append("Price above EMA-50 (uptrend confirmed)")
    if below_trend and sell_score > 0:
        sell_score += 1
        reasons.append("Price below EMA-50 (downtrend confirmed)")

    # ── Condition 3: RSI filter ───────────────────────────────
    # BUY : RSI below overbought threshold → still has room to run
    if rsi < cfg.RSI_OVERBOUGHT and buy_score > 0:
        buy_score += 1
        reasons.append(f"RSI {rsi:.1f} — below overbought ({cfg.RSI_OVERBOUGHT}), room to run")

    # SELL: RSI overbought (prime exit) OR collapsed below oversold (momentum gone)
    # This is correct for a LONG-ONLY exit — we exit when the move is exhausted.
    if sell_score > 0 and (rsi > cfg.RSI_OVERBOUGHT or rsi < cfg.RSI_OVERSOLD):
        sell_score += 1
        if rsi > cfg.RSI_OVERBOUGHT:
            reasons.append(f"RSI {rsi:.1f} — overbought, long exhausted, exit now")
        else:
            reasons.append(f"RSI {rsi:.1f} — momentum collapsed, exit to protect capital")

    # ── Condition 4: Volume confirmation (bonus) ──────────────
    if "vol_spike" in latest.index and latest["vol_spike"]:
        if buy_score > 0:
            buy_score += 1
            reasons.append("Volume spike confirms bullish move")
        if sell_score > 0:
            sell_score += 1
            reasons.append("Volume spike confirms bearish move")

    # ── Determine signal ──────────────────────────────────────
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
        # Long-only exit — no new stop/target needed, just close at market.
        # We pass entry as current price so the dashboard can display it.
        return {
            "signal":      "SELL",
            "strength":    min(sell_score, 3),
            "reasons":     reasons,
            "entry":       round(price, 4),   # exit price (where we close the long)
            "stop_loss":   None,              # not applicable — we are closing, not shorting
            "take_profit": None,              # not applicable
            "atr":         round(atr, 4),
            "rsi":         round(rsi, 1),
        }

    else:
        return {
            "signal":      "HOLD",
            "strength":    0,
            "reasons":     reasons or ["No confluence — staying out"],
            "entry":       None,
            "stop_loss":   None,
            "take_profit": None,
            "atr":         round(atr, 4) if not pd.isna(atr) else None,
            "rsi":         round(rsi, 1) if not pd.isna(rsi) else None,
        }
