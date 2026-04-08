"""
risk/manager.py — Risk Management Engine
Handles position sizing, stop-loss, kill switch, daily loss tracking.
"""
import json
import os
from datetime import date
from config.settings import cfg


class RiskManager:
    def __init__(self, market: str = "US"):
        self.market = market
        if market == "US":
            self.capital = cfg.PAPER_CAPITAL_USD
            self.currency = "USD"
        elif market == "CRYPTO":
            self.capital = cfg.PAPER_CAPITAL_USD   # USDT — same scale as USD
            self.currency = "USDT"
        else:  # NSE
            self.capital = cfg.PAPER_CAPITAL_INR
            self.currency = "INR"

        self.trades_today = 0
        self.pnl_today = 0.0
        self.trade_log = []
        self._load_state()

    # ── State persistence ────────────────────────────────────
    def _state_file(self) -> str:
        return f"logs/risk_state_{self.market}_{date.today()}.json"

    def _load_state(self):
        path = self._state_file()
        if os.path.exists(path):
            with open(path) as f:
                s = json.load(f)
            self.trades_today = s.get("trades_today", 0)
            self.pnl_today = s.get("pnl_today", 0.0)
            self.trade_log = s.get("trade_log", [])

    def _save_state(self):
        os.makedirs("logs", exist_ok=True)
        with open(self._state_file(), "w") as f:
            json.dump({
                "trades_today": self.trades_today,
                "pnl_today": self.pnl_today,
                "trade_log": self.trade_log,
            }, f, indent=2)

    # ── Core checks ──────────────────────────────────────────
    def can_trade(self) -> tuple:
        """Returns (allowed: bool, reason: str). Call before every trade."""
        if self.trades_today >= cfg.MAX_TRADES_PER_DAY:
            return False, f"Max trades/day reached ({cfg.MAX_TRADES_PER_DAY})"

        if self.pnl_today < 0:
            loss_pct = abs(self.pnl_today) / self.capital * 100
            if loss_pct >= cfg.MAX_DAILY_LOSS_PCT:
                return False, (
                    f"🔴 KILL SWITCH: Daily loss {loss_pct:.1f}% "
                    f"≥ limit {cfg.MAX_DAILY_LOSS_PCT}%"
                )
        return True, "OK"

    # ── Position sizing ───────────────────────────────────────
    def position_size(self, entry: float, stop: float) -> dict:
        """
        Fixed-fraction sizing: risk exactly RISK_PER_TRADE_PCT% of capital.
        Returns qty, risk_amount, stop_loss, take_profit.
        """
        risk_amount = self.capital * (cfg.RISK_PER_TRADE_PCT / 100)
        risk_per_unit = abs(entry - stop)
        if risk_per_unit <= 0:
            return {}
        qty = int(risk_amount / risk_per_unit)
        take_profit = entry + (risk_per_unit * cfg.MIN_RR_RATIO)
        return {
            "qty": qty,
            "entry": round(entry, 4),
            "stop_loss": round(stop, 4),
            "take_profit": round(take_profit, 4),
            "risk_amount": round(risk_amount, 2),
            "rr_ratio": cfg.MIN_RR_RATIO,
            "currency": self.currency,
        }

    # ── Trade recording ───────────────────────────────────────
    def record_trade(self, symbol: str, side: str, entry: float,
                     qty, stop: float, target: float):
        self.trades_today += 1
        self.trade_log.append({
            "date": str(date.today()),
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "qty": qty,
            "stop": stop,
            "target": target,
            "status": "OPEN",
            "pnl": 0.0,
        })
        self._save_state()

    def close_trade(self, symbol: str, exit_price: float) -> float:
        for t in reversed(self.trade_log):
            if t["symbol"] == symbol and t["status"] == "OPEN":
                pnl = (exit_price - t["entry"]) * t["qty"]
                t["pnl"] = round(pnl, 2)
                t["status"] = "CLOSED"
                t["exit"] = exit_price
                self.pnl_today += pnl
                self._save_state()
                return round(pnl, 2)
        return 0.0

    # ── Summary ───────────────────────────────────────────────
    def daily_summary(self) -> dict:
        closed = [t for t in self.trade_log if t["status"] == "CLOSED"]
        wins = [t for t in closed if t["pnl"] > 0]
        return {
            "market": self.market,
            "trades_today": self.trades_today,
            "pnl_today": round(self.pnl_today, 2),
            "win_rate": f"{len(wins) / len(closed) * 100:.1f}%" if closed else "N/A",
            "open_trades": len([t for t in self.trade_log if t["status"] == "OPEN"]),
            "currency": self.currency,
        }
