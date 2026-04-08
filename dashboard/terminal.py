"""
dashboard/terminal.py — Live Terminal Dashboard
Displays real-time P&L, signals, and positions for all 3 markets.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from datetime import datetime

console = Console()


def pnl_color(val: float) -> str:
    if val > 0:
        return "green"
    if val < 0:
        return "red"
    return "white"


def render_dashboard(
    us_portfolio: dict,
    nse_portfolio: dict,
    us_risk: dict,
    nse_risk: dict,
    last_signals: list,
    crypto_port: dict = None,
    crypto_summary: dict = None,
):
    console.clear()

    # ── Header ────────────────────────────────────────────────
    console.print(Panel(
        f"[bold cyan]🤖 AUTOMATED TRADING AGENT[/] "
        f"[dim]| PAPER MODE | {datetime.now().strftime('%d %b %Y %H:%M:%S')}[/]",
        style="bold"
    ))

    # ── P&L Cards ─────────────────────────────────────────────
    us_pnl = us_portfolio.get("pnl_today", 0)
    nse_pnl = nse_portfolio.get("total_pnl", 0)

    us_card = Panel(
        f"[bold]Portfolio[/]: ${us_portfolio.get('portfolio_value', 0):,.2f}\n"
        f"[bold]Cash[/]:      ${us_portfolio.get('cash', 0):,.2f}\n"
        f"[bold]P&L Today[/]: [{pnl_color(us_pnl)}]{'+' if us_pnl >= 0 else ''}{us_pnl:.2f}[/]\n"
        f"[bold]Positions[/]: {us_portfolio.get('open_positions', 0)}\n"
        f"[bold]Trades[/]:    {us_risk.get('trades_today', 0)}/{us_risk.get('max_trades', 10)}\n"
        f"[bold]Win Rate[/]:  {us_risk.get('win_rate', 'N/A')}",
        title="🇺🇸 US Stocks (Alpaca Paper)",
        border_style="blue"
    )

    nse_card = Panel(
        f"[bold]Cash[/]:        ₹{nse_portfolio.get('cash', 0):,.2f}\n"
        f"[bold]Unrealised[/]:  [{pnl_color(nse_pnl)}]{'+' if nse_pnl >= 0 else ''}₹{nse_portfolio.get('unrealized_pnl', 0):.2f}[/]\n"
        f"[bold]Realised[/]:    [{pnl_color(nse_pnl)}]{'+' if nse_pnl >= 0 else ''}₹{nse_portfolio.get('realized_pnl', 0):.2f}[/]\n"
        f"[bold]Positions[/]:   {nse_portfolio.get('open_positions', 0)}\n"
        f"[bold]Trades[/]:      {nse_risk.get('trades_today', 0)}/{nse_risk.get('max_trades', 10)}\n"
        f"[bold]Win Rate[/]:    {nse_risk.get('win_rate', 'N/A')}",
        title="🇮🇳 NSE India (Paper)",
        border_style="green"
    )

    if crypto_port and crypto_summary:
        c_pnl = crypto_port.get("unrealized_pnl", 0)
        crypto_card = Panel(
            f"[bold]USDT Balance[/]: ${crypto_port.get('cash', 0):,.2f}\n"
            f"[bold]P&L Today[/]:    [{pnl_color(c_pnl)}]{'+' if c_pnl >= 0 else ''}{c_pnl:.2f} USDT[/]\n"
            f"[bold]Positions[/]:    {crypto_port.get('positions', 0)}\n"
            f"[bold]Trades[/]:       {crypto_summary.get('trades_today', 0)}/{crypto_summary.get('max_trades', 10)}\n"
            f"[bold]Win Rate[/]:     {crypto_summary.get('win_rate', 'N/A')}\n"
            f"[bold]Market[/]:       24/7 ✅",
            title="₿  Crypto (Binance Testnet)",
            border_style="yellow"
        )
        console.print(Columns([us_card, nse_card, crypto_card]))
    else:
        console.print(Columns([us_card, nse_card]))

    # ── Recent Signals ────────────────────────────────────────
    if last_signals:
        sig_table = Table(title="Recent Signals", border_style="dim")
        sig_table.add_column("Time",   style="dim")
        sig_table.add_column("Market", style="dim")
        sig_table.add_column("Symbol", style="bold")
        sig_table.add_column("Signal", justify="center")
        sig_table.add_column("RSI",    justify="right")
        sig_table.add_column("Entry",  justify="right")
        sig_table.add_column("Stop",   justify="right")
        sig_table.add_column("Target", justify="right")

        for s in last_signals[-8:]:
            sig_val = s["signal"]
            sig_color = "green" if sig_val == "BUY" else ("red" if sig_val == "SELL" else "dim")
            sig_table.add_row(
                s.get("time", "--"),
                s.get("market", "--"),
                s.get("symbol", "--"),
                f"[{sig_color}]{sig_val}[/]",
                str(round(s.get("rsi", 0), 1) if s.get("rsi") else "--"),
                str(s.get("entry", "--")),
                str(s.get("stop_loss", "--")),
                str(s.get("take_profit", "--")),
            )
        console.print(sig_table)

    console.print("[dim]Refreshes every 60s · Ctrl+C to stop[/]")


def print_signal(market: str, symbol: str, signal: dict):
    """Quick inline signal print during scan — only for confirmed actionable signals."""
    color = "green" if signal["signal"] == "BUY" else "red"
    console.print(
        f"  [{color}]{signal['signal']}[/] {symbol} ({market}) | "
        f"RSI: {signal.get('rsi', '?')} | "
        f"Entry: {signal.get('entry', '?')} | "
        f"Stop: {signal.get('stop_loss', '?')} | "
        f"Target: {signal.get('take_profit', '?')}"
    )
