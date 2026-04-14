"""
main.py — Trading Agent Orchestrator
Runs the full pipeline: scan → signal → risk check → execute → alert

Usage:
  python main.py            # Run continuously (scans every 5 min)
  python main.py --once     # One scan cycle and exit
  python main.py --summary  # Print portfolio summary and exit
"""

import time
import argparse
from datetime import datetime

from config.settings import cfg
from strategies.signal_engine import generate_signal
from risk.manager import RiskManager
from alerts.telegram_alert import TelegramAlert
from brokers.alpaca_broker import AlpacaBroker
from brokers.nse_broker import NSEPaperBroker
from brokers.binance_broker import BinanceBroker
from dashboard.terminal import render_dashboard, print_signal, console

# Validate .env keys on startup — fails fast with a clear message
# instead of a cryptic HTTP 401 on the first live order.
cfg.validate()

# ── Module-level singletons ───────────────────────────────────
alert         = TelegramAlert()
us_broker     = AlpacaBroker()
nse_broker    = NSEPaperBroker()
crypto_broker = BinanceBroker()
us_risk       = RiskManager(market="US")
nse_risk      = RiskManager(market="NSE")
crypto_risk   = RiskManager(market="CRYPTO")
signal_log    = []   # recent signals shown on the dashboard


# ── Helpers ───────────────────────────────────────────────────
def _has_position(broker, symbol: str) -> bool:
    return symbol in broker.positions and broker.positions[symbol].get("qty", 0) > 0


def _signal_is_actionable(sig: dict, broker, symbol: str):
    """
    Long-only discipline:
      BUY  — only when we do NOT already hold the symbol
      SELL — only when we DO hold the symbol (close the long)
    Returns (ok: bool, reason: str)
    """
    direction = sig["signal"]
    holding   = _has_position(broker, symbol)
    if direction == "BUY" and holding:
        return False, "Already in position — BUY skipped"
    if direction == "SELL" and not holding:
        return False, "No position held — SELL skipped"
    return True, ""


# ── US scan ───────────────────────────────────────────────────
def scan_us():
    if not us_broker.is_market_open():
        console.print("[dim]🇺🇸 US market closed — skipping[/]")
        return

    console.print("[bold blue]🇺🇸 Scanning US watchlist...[/]")

    for ex in us_broker.check_stops():
        console.print(f"  [yellow]Auto-exit: {ex['symbol']} — {ex['reason']} @ {ex['price']}[/]")
        pnl = us_risk.close_trade(ex["symbol"], ex["price"])
        alert.trade_exit("US", ex["symbol"], ex["reason"], pnl, "USD")

    for symbol in cfg.US_WATCHLIST:
        try:
            df = us_broker.get_bars(symbol, timeframe="1Hour", limit=100)
            if df.empty or len(df) < 55:
                continue

            sig = generate_signal(df, market="US")

            if sig["signal"] not in ("BUY", "SELL"):
                signal_log.append({"time": datetime.now().strftime("%H:%M"),
                                   "market": "US", "symbol": symbol, **sig})
                continue

            ok, reason = _signal_is_actionable(sig, us_broker, symbol)
            if not ok:
                console.print(f"  [dim]{symbol}: {reason}[/]")
                signal_log.append({"time": datetime.now().strftime("%H:%M"),
                                   "market": "US", "symbol": symbol, **sig})
                continue

            allowed, block_reason = us_risk.can_trade()
            if not allowed:
                console.print(f"  [red]Blocked: {block_reason}[/]")
                if "KILL SWITCH" in block_reason:
                    alert.kill_switch("US", block_reason, us_risk.pnl_today, "USD")
                continue

            pos = us_risk.position_size(sig["entry"], sig["stop_loss"])
            if not pos or pos["qty"] < 1:
                console.print(f"  [dim]{symbol}: position size 0 — skip[/]")
                continue

            side = "buy" if sig["signal"] == "BUY" else "sell"
            try:
                order = us_broker.place_order(
                    symbol, pos["qty"], side,
                    pos["stop_loss"], pos["take_profit"]
                )
                us_risk.record_trade(
                    symbol, sig["signal"], sig["entry"],
                    pos["qty"], pos["stop_loss"], pos["take_profit"]
                )
                print_signal("US", symbol, sig)
                alert.signal("US", symbol, sig)
                alert.trade_executed(
                    "US", symbol, sig["signal"], pos["qty"],
                    sig["entry"], pos["stop_loss"], pos["take_profit"]
                )
                console.print(f"  [green]✓ Order placed: {order.get('id', '?')}[/]")
            except Exception as e:
                console.print(f"  [red]Order failed: {e}[/]")

            signal_log.append({"time": datetime.now().strftime("%H:%M"),
                               "market": "US", "symbol": symbol, **sig})
        except Exception as e:
            console.print(f"  [red]Error scanning {symbol}: {e}[/]")


# ── NSE scan ──────────────────────────────────────────────────
def scan_nse():
    if not nse_broker.is_market_open():
        console.print("[dim]🇮🇳 NSE market closed — skipping[/]")
        return

    console.print("[bold green]🇮🇳 Scanning NSE watchlist...[/]")

    for ex in nse_broker.check_stops():
        console.print(f"  [yellow]Auto-exit: {ex['symbol']} — {ex['reason']} @ {ex['price']}[/]")
        pnl = nse_risk.close_trade(ex["symbol"], ex["price"])
        alert.trade_exit("NSE", ex["symbol"], ex["reason"], pnl, "INR")

    for symbol in cfg.NSE_WATCHLIST:
        try:
            df = nse_broker.get_bars(symbol, period="60d", interval="1h")
            if df.empty or len(df) < 55:
                continue

            sig = generate_signal(df, market="NSE")

            if sig["signal"] not in ("BUY", "SELL"):
                signal_log.append({"time": datetime.now().strftime("%H:%M"),
                                   "market": "NSE", "symbol": symbol, **sig})
                continue

            ok, reason = _signal_is_actionable(sig, nse_broker, symbol)
            if not ok:
                console.print(f"  [dim]{symbol}: {reason}[/]")
                signal_log.append({"time": datetime.now().strftime("%H:%M"),
                                   "market": "NSE", "symbol": symbol, **sig})
                continue

            allowed, block_reason = nse_risk.can_trade()
            if not allowed:
                console.print(f"  [red]Blocked: {block_reason}[/]")
                if "KILL SWITCH" in block_reason:
                    alert.kill_switch("NSE", block_reason, nse_risk.pnl_today, "INR")
                continue

            pos = nse_risk.position_size(sig["entry"], sig["stop_loss"])
            if not pos or pos["qty"] < 1:
                continue

            try:
                order = nse_broker.place_order(
                    symbol, pos["qty"], sig["signal"],
                    pos["stop_loss"], pos["take_profit"]
                )
                nse_risk.record_trade(
                    symbol, sig["signal"], sig["entry"],
                    pos["qty"], pos["stop_loss"], pos["take_profit"]
                )
                print_signal("NSE", symbol, sig)
                alert.signal("NSE", symbol, sig)
                alert.trade_executed(
                    "NSE", symbol, sig["signal"], pos["qty"],
                    sig["entry"], pos["stop_loss"], pos["take_profit"]
                )
                console.print(f"  [green]✓ Paper order: {order['status']}[/]")
            except Exception as e:
                console.print(f"  [red]Order failed: {e}[/]")

            signal_log.append({"time": datetime.now().strftime("%H:%M"),
                               "market": "NSE", "symbol": symbol, **sig})
        except Exception as e:
            console.print(f"  [red]Error scanning {symbol}: {e}[/]")


# ── Crypto scan ───────────────────────────────────────────────
def scan_crypto():

    

    """Crypto is 24/7 — always runs regardless of market hours."""

    if cfg.ENABLE_CRYPTO:
        console.print("[dim]₿ Crypto disabled — pending 4h fix[/]")
        return
    
    console.print("[bold yellow]₿ Scanning Crypto watchlist...[/]")

    for ex in crypto_broker.check_stops():
        console.print(f"  [yellow]Auto-exit: {ex['symbol']} — {ex['reason']} @ {ex['price']}[/]")
        pnl = crypto_risk.close_trade(ex["symbol"], ex["price"])
        alert.trade_exit("CRYPTO", ex["symbol"], ex["reason"], pnl, "USDT")

    for symbol in cfg.CRYPTO_WATCHLIST:
        try:
            df = crypto_broker.get_bars(symbol, interval="1h", limit=100)
            if df.empty or len(df) < 55:
                continue

            # market="CRYPTO" → uses CRYPTO_ATR_MULTIPLIER=2.5, RSI 35/65
            sig = generate_signal(df, market="CRYPTO")

            if sig["signal"] not in ("BUY", "SELL"):
                signal_log.append({"time": datetime.now().strftime("%H:%M"),
                                   "market": "CRYPTO", "symbol": symbol, **sig})
                continue

            ok, reason = _signal_is_actionable(sig, crypto_broker, symbol)
            if not ok:
                console.print(f"  [dim]{symbol}: {reason}[/]")
                signal_log.append({"time": datetime.now().strftime("%H:%M"),
                                   "market": "CRYPTO", "symbol": symbol, **sig})
                continue

            allowed, block_reason = crypto_risk.can_trade()
            if not allowed:
                console.print(f"  [red]Blocked: {block_reason}[/]")
                if "KILL SWITCH" in block_reason:
                    alert.kill_switch("CRYPTO", block_reason, crypto_risk.pnl_today, "USDT")
                continue

            pos = crypto_risk.position_size(sig["entry"], sig["stop_loss"])
            if not pos or pos["qty"] <= 0:
                continue

            try:
                order = crypto_broker.place_order(
                    symbol, pos["qty"], sig["signal"],
                    pos["stop_loss"], pos["take_profit"]
                )
                crypto_risk.record_trade(
                    symbol, sig["signal"], sig["entry"],
                    pos["qty"], pos["stop_loss"], pos["take_profit"]
                )
                print_signal("CRYPTO", symbol, sig)
                alert.signal("CRYPTO", symbol, sig)
                alert.trade_executed(
                    "CRYPTO", symbol, sig["signal"], pos["qty"],
                    sig["entry"], pos["stop_loss"], pos["take_profit"]
                )
                console.print("  [green]✓ Crypto order placed[/]")
            except Exception as e:
                console.print(f"  [red]Order failed: {e}[/]")

            signal_log.append({"time": datetime.now().strftime("%H:%M"),
                               "market": "CRYPTO", "symbol": symbol, **sig})
        except Exception as e:
            console.print(f"  [red]Error scanning {symbol}: {e}[/]")


# ── One full scan cycle ───────────────────────────────────────
def run_scan():
    global signal_log
    signal_log = []
    console.rule(f"[dim]{datetime.now().strftime('%H:%M:%S')} — Scan cycle[/]")
    scan_us()
    scan_nse()
    scan_crypto()
    try:
        render_dashboard(
            us_broker.portfolio_summary(),
            nse_broker.portfolio_summary(),
            {**us_risk.daily_summary(),     "max_trades": cfg.MAX_TRADES_PER_DAY},
            {**nse_risk.daily_summary(),    "max_trades": cfg.MAX_TRADES_PER_DAY},
            signal_log,
            crypto_port    = crypto_broker.portfolio_summary(),
            crypto_summary = {**crypto_risk.daily_summary(),
                              "max_trades": cfg.MAX_TRADES_PER_DAY},
        )
    except Exception as e:
        console.print(f"[dim]Dashboard error: {e}[/]")


# ── Daily summary ─────────────────────────────────────────────
def send_daily_summary():
    alert.daily_summary(
        us_risk.daily_summary(),
        nse_risk.daily_summary(),
        crypto_risk.daily_summary(),
    )
    console.print("[bold]📊 Daily summary sent to Telegram[/]")


# ── Entry point ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Multi-market trading agent")
    parser.add_argument("--once",    action="store_true",
                        help="Run one scan cycle and exit")
    parser.add_argument("--summary", action="store_true",
                        help="Print portfolio summary and exit")
    args = parser.parse_args()

    console.print("[bold cyan]🤖 Trading Agent starting...[/]")
    alert.startup(["US Stocks (Alpaca Paper)", "NSE India (Paper)",
                   "Crypto (Binance Testnet)"])

    if args.summary:
        console.print_json(data={
            "US":     us_broker.portfolio_summary(),
            "NSE":    nse_broker.portfolio_summary(),
            "CRYPTO": crypto_broker.portfolio_summary(),
        })
        return

    if args.once:
        run_scan()
        return

    console.print("[green]Running continuously — scans every 5 minutes.[/]")
    console.print("[dim]Press Ctrl+C to stop.[/]")

    scan_count = 0
    while True:
        try:
            run_scan()
            scan_count += 1
            if scan_count % 50 == 0:   # every ~4 hours
                send_daily_summary()
            time.sleep(300)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping agent...[/]")
            send_daily_summary()
            break
        except Exception as e:
            console.print(f"[red]Main loop error: {e}[/]")
            time.sleep(60)


if __name__ == "__main__":
    main()
