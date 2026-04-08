"""
backtest.py — Strategy Backtester
Runs the signal engine over historical data and reports performance.

Usage:
    python backtest.py --market US --symbol AAPL --period 180d
    python backtest.py --market NSE --symbol RELIANCE --period 180d
    python backtest.py --market US --all    # backtest full watchlist
"""
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime
from rich.console import Console
from rich.table   import Table

from strategies.signal_engine import generate_signal
from config.settings          import cfg

console = Console()


def fetch_data(symbol: str, market: str, period: str = "180d") -> pd.DataFrame:
    ticker_sym = f"{symbol}.NS" if market == "NSE" else symbol
    df = yf.download(ticker_sym, period=period, interval="1h", progress=False)
    if df.empty:
        return pd.DataFrame()
    df.columns = df.columns.get_level_values(0).str.lower()
    return df[["open", "high", "low", "close", "volume"]].dropna()


def run_backtest(symbol: str, market: str, period: str = "180d",
                 capital: float = 10000) -> dict:
    df = fetch_data(symbol, market, period)
    if df.empty or len(df) < 60:
        return {"error": f"Insufficient data for {symbol}"}

    trades       = []
    in_position  = False
    entry_price  = 0.0
    stop_loss    = 0.0
    take_profit  = 0.0
    position_qty = 0
    side         = ""

    for i in range(55, len(df)):
        window = df.iloc[:i]
        sig    = generate_signal(window)
        price  = float(df.iloc[i]["close"])

        # ── Check exits first ──────────────────────────────────
        if in_position:
            pnl = 0.0
            exit_reason = None

            if side == "BUY":
                if price <= stop_loss:
                    pnl         = (stop_loss - entry_price) * position_qty
                    exit_reason = "STOP_LOSS"
                elif price >= take_profit:
                    pnl         = (take_profit - entry_price) * position_qty
                    exit_reason = "TAKE_PROFIT"
            elif side == "SELL":
                if price >= stop_loss:
                    pnl         = (entry_price - stop_loss) * position_qty
                    exit_reason = "STOP_LOSS"
                elif price <= take_profit:
                    pnl         = (entry_price - take_profit) * position_qty
                    exit_reason = "TAKE_PROFIT"

            if exit_reason:
                capital += pnl
                trades.append({
                    "symbol":      symbol,
                    "side":        side,
                    "entry":       entry_price,
                    "exit":        stop_loss if exit_reason == "STOP_LOSS" else take_profit,
                    "qty":         position_qty,
                    "pnl":         round(pnl, 2),
                    "exit_reason": exit_reason,
                    "date":        str(df.index[i].date()),
                })
                in_position = False
            continue

        # ── New signal ─────────────────────────────────────────
        if not in_position and sig["signal"] in ("BUY", "SELL"):
            risk_amount  = capital * (cfg.RISK_PER_TRADE_PCT / 100)
            risk_per_unit = abs(sig["entry"] - sig["stop_loss"])
            if risk_per_unit <= 0:
                continue

            position_qty = max(1, int(risk_amount / risk_per_unit))
            entry_price  = sig["entry"]
            stop_loss    = sig["stop_loss"]
            take_profit  = sig["take_profit"]
            side         = sig["signal"]
            in_position  = True

    # ── Stats ─────────────────────────────────────────────────
    if not trades:
        return {"symbol": symbol, "trades": 0, "error": "No trades generated"}

    wins       = [t for t in trades if t["pnl"] > 0]
    losses     = [t for t in trades if t["pnl"] <= 0]
    total_pnl  = sum(t["pnl"] for t in trades)
    win_rate   = len(wins) / len(trades) * 100
    avg_win    = sum(t["pnl"] for t in wins)  / max(len(wins), 1)
    avg_loss   = sum(t["pnl"] for t in losses)/ max(len(losses), 1)
    profit_factor = abs(avg_win * len(wins)) / max(abs(avg_loss * len(losses)), 0.01)

    return {
        "symbol":        symbol,
        "market":        market,
        "period":        period,
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
    table = Table(title="📊 Backtest Results", border_style="dim")
    table.add_column("Symbol",  style="bold")
    table.add_column("Market",  style="dim")
    table.add_column("Trades",  justify="right")
    table.add_column("Win %",   justify="right")
    table.add_column("Total P&L",    justify="right")
    table.add_column("Avg Win",      justify="right")
    table.add_column("Avg Loss",     justify="right")
    table.add_column("Profit Factor",justify="right")
    table.add_column("Return %",     justify="right")

    for r in results:
        if "error" in r:
            table.add_row(r.get("symbol","?"), r.get("market","?"),
                          "—","—","—","—","—","—",f"[red]{r['error']}[/]")
            continue
        ret    = r["return_pct"]
        pnl    = r["total_pnl"]
        color  = "green" if ret >= 0 else "red"
        table.add_row(
            r["symbol"],
            r["market"],
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
    parser.add_argument("--market",  default="US",    choices=["US","NSE"])
    parser.add_argument("--symbol",  default="AAPL")
    parser.add_argument("--period",  default="180d")
    parser.add_argument("--all",     action="store_true", help="Backtest full watchlist")
    args = parser.parse_args()

    console.print("[bold cyan]📊 Running backtests...[/]")

    if args.all:
        watchlist = cfg.US_WATCHLIST if args.market == "US" else cfg.NSE_WATCHLIST
        results = []
        for sym in watchlist:
            console.print(f"  Testing {sym}...")
            results.append(run_backtest(sym, args.market, args.period))
        print_results(results)
    else:
        result = run_backtest(args.symbol, args.market, args.period)
        print_results([result])

        # Print individual trades
        if "trades" in result and result["trades"]:
            t_table = Table(title=f"Trade Log — {args.symbol}", border_style="dim")
            t_table.add_column("Date")
            t_table.add_column("Side")
            t_table.add_column("Entry",  justify="right")
            t_table.add_column("Exit",   justify="right")
            t_table.add_column("Qty",    justify="right")
            t_table.add_column("P&L",    justify="right")
            t_table.add_column("Reason")
            for t in result["trades"][-20:]:  # last 20
                pnl   = t["pnl"]
                color = "green" if pnl > 0 else "red"
                t_table.add_row(
                    t["date"], t["side"],
                    str(t["entry"]), str(t["exit"]),
                    str(t["qty"]),
                    f"[{color}]{'+' if pnl >= 0 else ''}{pnl:.2f}[/]",
                    t["exit_reason"],
                )
            console.print(t_table)
