"""
backtest_crypto.py — Crypto Strategy Backtester
Uses Binance public API (no keys needed) for historical data.

Usage:
  python backtest_crypto.py --symbol BTCUSDT --interval 1h --period 180
  python backtest_crypto.py --all --interval 1h
"""
import argparse
import time
import pandas as pd
import requests
from rich.console import Console
from rich.table import Table
from strategies.signal_engine import generate_signal
from config.settings import cfg

console = Console()
BINANCE_PUBLIC = "https://api.binance.com"   # Public endpoint — no keys needed for history


def fetch_data(symbol: str, interval: str = "1h", days: int = 180) -> pd.DataFrame:
    limit = min(days * 24, 1000)   # Binance max = 1000 candles per request
    try:
        r = requests.get(f"{BINANCE_PUBLIC}/api/v3/klines", params={
            "symbol": symbol, "interval": interval, "limit": limit,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","quote_vol","trades","taker_base","taker_quote","ignore"
        ])
        df = df[["open","high","low","close","volume"]].astype(float)
        return df
    except Exception as e:
        console.print(f"[red]Fetch error for {symbol}: {e}[/]")
        return pd.DataFrame()


def run_backtest(symbol: str, interval: str = "1h",
                 days: int = 180, capital: float = 10000) -> dict:
    df = fetch_data(symbol, interval, days)
    if df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "Insufficient data"}

    trades, in_position = [], False
    entry_price = stop_loss = take_profit = 0.0
    position_qty = 0
    side = ""

    for i in range(55, len(df)):
        window = df.iloc[:i]
        sig    = generate_signal(window)
        price  = float(df.iloc[i]["close"])

        if in_position:
            pnl, exit_reason = 0.0, None
            if side == "BUY":
                if price <= stop_loss:
                    pnl, exit_reason = (stop_loss - entry_price) * position_qty, "STOP_LOSS"
                elif price >= take_profit:
                    pnl, exit_reason = (take_profit - entry_price) * position_qty, "TAKE_PROFIT"
            else:
                if price >= stop_loss:
                    pnl, exit_reason = (entry_price - stop_loss) * position_qty, "STOP_LOSS"
                elif price <= take_profit:
                    pnl, exit_reason = (entry_price - take_profit) * position_qty, "TAKE_PROFIT"

            if exit_reason:
                capital += pnl
                trades.append({
                    "symbol": symbol, "side": side,
                    "entry": entry_price,
                    "exit":  stop_loss if exit_reason == "STOP_LOSS" else take_profit,
                    "qty":   position_qty, "pnl": round(pnl, 2),
                    "exit_reason": exit_reason,
                })
                in_position = False
                continue

        if not in_position and sig["signal"] in ("BUY", "SELL"):
            risk_amount  = capital * (cfg.RISK_PER_TRADE_PCT / 100)
            risk_per_unit = abs(sig["entry"] - sig["stop_loss"])
            if risk_per_unit <= 0:
                continue
            position_qty = max(0.001, round(risk_amount / risk_per_unit, 6))
            entry_price  = sig["entry"]
            stop_loss    = sig["stop_loss"]
            take_profit  = sig["take_profit"]
            side         = sig["signal"]
            in_position  = True

    if not trades:
        return {"symbol": symbol, "error": "No trades generated"}

    wins        = [t for t in trades if t["pnl"] > 0]
    losses      = [t for t in trades if t["pnl"] <= 0]
    total_pnl   = sum(t["pnl"] for t in trades)
    win_rate    = len(wins) / len(trades) * 100
    avg_win     = sum(t["pnl"] for t in wins)  / max(len(wins), 1)
    avg_loss    = sum(t["pnl"] for t in losses) / max(len(losses), 1)
    profit_factor = abs(avg_win * len(wins)) / max(abs(avg_loss * len(losses)), 0.01)

    return {
        "symbol":        symbol,
        "interval":      interval,
        "total_trades":  len(trades),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate_pct":  round(win_rate, 1),
        "total_pnl":     round(total_pnl, 2),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "final_capital": round(capital, 2),
        "return_pct":    round((capital - 10000) / 10000 * 100, 2),
        "trades":        trades,
    }


def print_results(results: list):
    table = Table(title="📊 Crypto Backtest Results", border_style="dim")
    table.add_column("Symbol",        style="bold")
    table.add_column("Interval",      style="dim")
    table.add_column("Trades",        justify="right")
    table.add_column("Win %",         justify="right")
    table.add_column("Total P&L",     justify="right")
    table.add_column("Avg Win",       justify="right")
    table.add_column("Avg Loss",      justify="right")
    table.add_column("Profit Factor", justify="right")
    table.add_column("Return %",      justify="right")

    for r in results:
        if "error" in r:
            table.add_row(r.get("symbol","?"), "—","—","—","—","—","—","—",
                          f"[red]{r['error']}[/]")
            continue
        ret   = r["return_pct"]
        pnl   = r["total_pnl"]
        color = "green" if ret >= 0 else "red"
        table.add_row(
            r["symbol"], r["interval"],
            str(r["total_trades"]),
            f"{r['win_rate_pct']}%",
            f"[{color}]{'+' if pnl >= 0 else ''}{pnl:.2f}[/]",
            f"[green]+{r['avg_win']:.2f}[/]",
            f"[red]{r['avg_loss']:.2f}[/]",
            str(r["profit_factor"]),
            f"[{color}]{'+' if ret >= 0 else ''}{ret:.1f}%[/]",
        )
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol",   default="BTCUSDT")
    parser.add_argument("--interval", default="1h",
                        choices=["5m","15m","1h","4h","1d"])
    parser.add_argument("--period",   default=180, type=int,
                        help="Days of history (max 1000 candles)")
    parser.add_argument("--all",      action="store_true",
                        help="Backtest full CRYPTO_WATCHLIST")
    args = parser.parse_args()

    console.print("[bold cyan]📊 Running crypto backtests...[/]")

    if args.all:
        results = []
        for sym in cfg.CRYPTO_WATCHLIST:
            console.print(f"  Testing {sym}...")
            results.append(run_backtest(sym, args.interval, args.period))
            time.sleep(0.3)   # avoid rate limit
        print_results(results)
    else:
        result = run_backtest(args.symbol, args.interval, args.period)
        print_results([result])

        if "trades" in result and result["trades"]:
            t_table = Table(title=f"Trade Log — {args.symbol}", border_style="dim")
            for col in ["Side","Entry","Exit","Qty","P&L","Reason"]:
                t_table.add_column(col, justify="right" if col not in ("Side","Reason") else "left")
            for t in result["trades"][-20:]:
                pnl   = t["pnl"]
                color = "green" if pnl > 0 else "red"
                t_table.add_row(
                    t["side"], str(t["entry"]), str(t["exit"]),
                    str(t["qty"]),
                    f"[{color}]{'+' if pnl >= 0 else ''}{pnl:.2f}[/]",
                    t["exit_reason"],
                )
            console.print(t_table)
