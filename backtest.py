"""
backtest.py — Strategy Backtester
Runs the signal engine over historical OHLCV data and reports performance.

Usage:
  python backtest.py --market US     --symbol AAPL     --period 180d
  python backtest.py --market NSE    --symbol RELIANCE --period 180d
  python backtest.py --market CRYPTO --symbol BTCUSDT  --period 180d
  python backtest.py --market US     --all             --period 180d
"""
import argparse
import pandas as pd
import yfinance as yf
from rich.console import Console
from rich.table import Table

from strategies.signal_engine import generate_signal
from config.settings import cfg

console = Console()


def fetch_data(symbol: str, market: str, period: str = "180d") -> pd.DataFrame:
    """
    Download hourly OHLCV data via yfinance.
    NSE    : appends .NS   (e.g. RELIANCE.NS)
    CRYPTO : converts USDT pairs to yfinance format (BTCUSDT -> BTC-USD)
    US     : symbol as-is  (e.g. AAPL)

    Always returns a pd.DataFrame — empty DataFrame on any failure.
    """
    if market == "NSE":
        ticker = f"{symbol}.NS"
    elif market == "CRYPTO":
        ticker = symbol.replace("USDT", "-USD")
    else:
        ticker = symbol

    try:
        result = yf.download(ticker, period=period, interval="1h",
                             progress=False, auto_adjust=True)
        # yf.download can return None on network/parse errors
        if result is None:
            return pd.DataFrame()
        if result.empty:
            return pd.DataFrame()
        # Flatten multi-level columns (yfinance >= 0.2.x returns MultiIndex)
        if isinstance(result.columns, pd.MultiIndex):
            result.columns = result.columns.get_level_values(0)
        result.columns = result.columns.str.lower()
        # Keep only the OHLCV columns we need
        required = {"open", "high", "low", "close", "volume"}
        available = required & set(result.columns)
        if not available.issuperset({"open", "high", "low", "close"}):
            return pd.DataFrame()
        return result[sorted(available, key=lambda c: list(required).index(c))].dropna()
    except Exception:
        return pd.DataFrame()


def run_backtest(symbol: str, market: str, period: str = "180d",
                 capital: float = 10_000) -> dict:
    """
    Long-only backtest: BUY entries only.
    Crypto uses CRYPTO_ATR_MULTIPLIER and tighter RSI bands via market arg.
    """
    df = fetch_data(symbol, market, period)
    if df.empty or len(df) < 60:
        return {
            "symbol": symbol,
            "market": market,
            "error": f"Insufficient data for {symbol} ({market})",
        }

    initial      = capital
    trades: list = []
    in_position  = False
    entry_price  = 0.0
    stop_loss    = 0.0
    take_profit  = 0.0
    position_qty = 0

    for i in range(55, len(df)):
        window = df.iloc[:i].copy()
        sig    = generate_signal(window, market=market)
        price  = float(df.iloc[i]["close"])

        # Check exit on open long
        if in_position:
            exit_reason: str | None = None
            pnl = 0.0

            if price <= stop_loss:
                pnl         = (stop_loss   - entry_price) * position_qty
                exit_reason = "STOP_LOSS"
            elif price >= take_profit:
                pnl         = (take_profit - entry_price) * position_qty
                exit_reason = "TAKE_PROFIT"

            if exit_reason:
                capital += pnl
                trades.append({
                    "symbol":      symbol,
                    "side":        "BUY",
                    "entry":       entry_price,
                    "exit":        stop_loss if exit_reason == "STOP_LOSS" else take_profit,
                    "qty":         position_qty,
                    "pnl":         round(pnl, 2),
                    "exit_reason": exit_reason,
                    "date":        str(df.index[i].date()),
                })
                in_position = False
            continue

        # New BUY entry
        if (
            not in_position
            and sig["signal"] == "BUY"
            and sig["stop_loss"] is not None
            and sig["take_profit"] is not None
        ):
            risk_amount   = capital * (cfg.RISK_PER_TRADE_PCT / 100)
            risk_per_unit = abs(float(sig["entry"]) - float(sig["stop_loss"]))
            if risk_per_unit <= 0:
                continue

            position_qty = max(1, int(risk_amount / risk_per_unit))
            entry_price  = float(sig["entry"])
            stop_loss    = float(sig["stop_loss"])
            take_profit  = float(sig["take_profit"])
            in_position  = True

    if not trades:
        return {
            "symbol": symbol,
            "market": market,
            "trades": 0,
            "error":  "No trades generated — try a longer period or check data",
        }

    wins          = [t for t in trades if t["pnl"] > 0]
    losses        = [t for t in trades if t["pnl"] <= 0]
    total_pnl     = sum(t["pnl"] for t in trades)
    win_rate      = len(wins) / len(trades) * 100
    avg_win       = sum(t["pnl"] for t in wins)   / max(len(wins),   1)
    avg_loss      = sum(t["pnl"] for t in losses) / max(len(losses), 1)
    profit_factor = (
        abs(avg_win * len(wins))
        / max(abs(avg_loss * len(losses)), 0.01)
    )

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
        "return_pct":    round((capital - initial) / initial * 100, 2),
        "trades":        trades,
    }


def print_results(results: list) -> None:
    table = Table(title="Backtest Results", border_style="dim")
    table.add_column("Symbol",        style="bold")
    table.add_column("Market",        style="dim")
    table.add_column("Trades",        justify="right")
    table.add_column("Win %",         justify="right")
    table.add_column("Total P&L",     justify="right")
    table.add_column("Avg Win",       justify="right")
    table.add_column("Avg Loss",      justify="right")
    table.add_column("Profit Factor", justify="right")
    table.add_column("Return %",      justify="right")

    for r in results:
        if "error" in r:
            table.add_row(
                r.get("symbol", "?"), r.get("market", "?"),
                "-", "-", "-", "-", "-", "-",
                f"[red]{r['error']}[/]",
            )
            continue
        ret   = r["return_pct"]
        pnl   = r["total_pnl"]
        color = "green" if ret >= 0 else "red"
        sign  = "+" if pnl >= 0 else ""
        rsign = "+" if ret >= 0 else ""
        table.add_row(
            r["symbol"], r["market"],
            str(r["total_trades"]),
            f"{r['win_rate_pct']}%",
            f"[{color}]{sign}{pnl:.2f}[/]",
            f"[green]+{r['avg_win']:.2f}[/]",
            f"[red]{r['avg_loss']:.2f}[/]",
            str(r["profit_factor"]),
            f"[{color}]{rsign}{ret:.1f}%[/]",
        )
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest the signal engine")
    parser.add_argument("--market", default="US",
                        choices=["US", "NSE", "CRYPTO"])
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--period", default="180d")
    parser.add_argument("--all", action="store_true",
                        help="Backtest full watchlist for the chosen market")
    args = parser.parse_args()

    console.print("[bold cyan]Running backtests...[/]")

    if args.all:
        watchlist = {
            "US":     cfg.US_WATCHLIST,
            "NSE":    cfg.NSE_WATCHLIST,
            "CRYPTO": cfg.CRYPTO_WATCHLIST,
        }[args.market]
        results = []
        for sym in watchlist:
            console.print(f"  Testing {sym}...")
            results.append(run_backtest(sym, args.market, args.period))
        print_results(results)
    else:
        result = run_backtest(args.symbol, args.market, args.period)
        print_results([result])

        if "trades" in result and isinstance(result.get("trades"), list) and result["trades"]:
            t_table = Table(title=f"Trade Log - {args.symbol}", border_style="dim")
            t_table.add_column("Date")
            t_table.add_column("Side")
            t_table.add_column("Entry",  justify="right")
            t_table.add_column("Exit",   justify="right")
            t_table.add_column("Qty",    justify="right")
            t_table.add_column("P&L",    justify="right")
            t_table.add_column("Reason")
            for t in result["trades"][-20:]:
                pnl   = t["pnl"]
                color = "green" if pnl > 0 else "red"
                sign  = "+" if pnl >= 0 else ""
                t_table.add_row(
                    t["date"], t["side"],
                    str(t["entry"]), str(t["exit"]),
                    str(t["qty"]),
                    f"[{color}]{sign}{pnl:.2f}[/]",
                    t["exit_reason"],
                )
            console.print(t_table)
