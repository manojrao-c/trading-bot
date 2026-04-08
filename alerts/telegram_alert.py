"""
alerts/telegram_alert.py — Telegram Notification System
Sends trade signals, P&L summaries, and kill switch alerts.
"""
import requests
from datetime import datetime
from config.settings import cfg


class TelegramAlert:
    def __init__(self):
        self.token = cfg.TELEGRAM_TOKEN
        self.chat_id = cfg.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

    def _send(self, message: str):
        if not self.enabled:
            print(f"[TELEGRAM DISABLED] {message}")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

    # ── Signal alert ─────────────────────────────────────────
    def signal(self, market: str, symbol: str, signal: dict):
        emoji = "🟢" if signal["signal"] == "BUY" else "🔴"
        stars = "⭐" * signal.get("strength", 1)
        reasons = "\n".join(f" • {r}" for r in signal.get("reasons", []))
        msg = (
            f"{emoji} <b>{signal['signal']} Signal — {market}</b>\n"
            f"Symbol: <b>{symbol}</b> {stars}\n"
            f"Entry:  {signal.get('entry', 'N/A')}\n"
            f"Stop:   {signal.get('stop_loss', 'N/A')}\n"
            f"Target: {signal.get('take_profit', 'N/A')}\n"
            f"RSI:    {signal.get('rsi', 'N/A')}\n\n"
            f"Why:\n{reasons}\n"
            f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self._send(msg)

    # ── Trade executed alert ──────────────────────────────────
    def trade_executed(self, market: str, symbol: str, side: str,
                       qty, entry: float, stop: float, target: float):
        emoji = "📈" if side == "BUY" else "📉"
        msg = (
            f"{emoji} <b>PAPER TRADE EXECUTED — {market}</b>\n"
            f"{side} {qty} × {symbol}\n"
            f"Entry:  {entry}\n"
            f"Stop:   {stop}\n"
            f"Target: {target}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self._send(msg)

    # ── Exit alert ────────────────────────────────────────────
    def trade_exit(self, market: str, symbol: str, reason: str,
                   pnl: float, currency: str):
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} <b>POSITION CLOSED — {market}</b>\n"
            f"Symbol: {symbol}\n"
            f"Reason: {reason}\n"
            f"P&L: {'+' if pnl >= 0 else ''}{pnl:.2f} {currency}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self._send(msg)

    # ── Kill switch alert ─────────────────────────────────────
    def kill_switch(self, market: str, reason: str, pnl: float, currency: str):
        msg = (
            f"🔴🔴 <b>KILL SWITCH TRIGGERED — {market}</b>\n"
            f"Reason: {reason}\n"
            f"Daily P&L: {pnl:.2f} {currency}\n"
            f"All trading halted for today.\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self._send(msg)

    # ── Daily summary — accepts all 3 markets ─────────────────
    def daily_summary(self, us_summary: dict, nse_summary: dict,
                      crypto_summary: dict = None):
        us_pnl = us_summary.get("pnl_today", 0)
        nse_pnl = nse_summary.get("pnl_today", 0)
        msg = (
            f"📊 <b>Daily Summary — {datetime.now().strftime('%d %b %Y')}</b>\n\n"
            f"🇺🇸 <b>US Stocks (Paper)</b>\n"
            f"  Trades:   {us_summary.get('trades_today', 0)}\n"
            f"  P&L:      {'+' if us_pnl >= 0 else ''}{us_pnl:.2f} USD\n"
            f"  Win Rate: {us_summary.get('win_rate', 'N/A')}\n\n"
            f"🇮🇳 <b>NSE India (Paper)</b>\n"
            f"  Trades:   {nse_summary.get('trades_today', 0)}\n"
            f"  P&L:      {'+' if nse_pnl >= 0 else ''}{nse_pnl:.2f} INR\n"
            f"  Win Rate: {nse_summary.get('win_rate', 'N/A')}"
        )
        if crypto_summary:
            c_pnl = crypto_summary.get("pnl_today", 0)
            msg += (
                f"\n\n₿ <b>Crypto (Binance Testnet)</b>\n"
                f"  Trades:   {crypto_summary.get('trades_today', 0)}\n"
                f"  P&L:      {'+' if c_pnl >= 0 else ''}{c_pnl:.2f} USDT\n"
                f"  Win Rate: {crypto_summary.get('win_rate', 'N/A')}"
            )
        self._send(msg)

    # ── Startup ───────────────────────────────────────────────
    def startup(self, markets: list):
        msg = (
            f"🤖 <b>Trading Agent Started</b>\n"
            f"Mode: PAPER TRADING (zero real money)\n"
            f"Markets: {', '.join(markets)}\n"
            f"🕐 {datetime.now().strftime('%d %b %Y %H:%M:%S')}"
        )
        self._send(msg)
