"""
brokers/nse_broker.py — NSE India Paper Trading Simulator
Uses yfinance for real NSE data, simulates order execution.
Real Zerodha Kite integration notes included for when you go live.
"""
import yfinance as yf
import pandas as pd
import json, os
from datetime import datetime, date
from config.settings import cfg


class NSEPaperBroker:
    """
    Paper trading broker for NSE India.
    Pulls real OHLCV data from Yahoo Finance (NSE suffix: .NS)
    Simulates orders locally — zero real money risk.

    When ready to go LIVE:
    - Replace with: from kiteconnect import KiteConnect
    - Zerodha Kite API: https://kite.trade (₹2000/month or free for Zerodha users)
    """

    def __init__(self):
        self.capital      = cfg.PAPER_CAPITAL_INR
        self.cash         = self.capital
        self.positions    = {}   # symbol → {qty, avg_entry, stop, target}
        self.order_log    = []
        self.pnl_realized = 0.0
        self._load_state()

    def _state_path(self):
        return f"logs/nse_paper_{date.today()}.json"

    def _load_state(self):
        p = self._state_path()
        if os.path.exists(p):
            with open(p) as f:
                s = json.load(f)
            self.cash         = s.get("cash", self.capital)
            self.positions    = s.get("positions", {})
            self.order_log    = s.get("order_log", [])
            self.pnl_realized = s.get("pnl_realized", 0.0)

    def _save_state(self):
        os.makedirs("logs", exist_ok=True)
        with open(self._state_path(), "w") as f:
            json.dump({
                "cash":         self.cash,
                "positions":    self.positions,
                "order_log":    self.order_log,
                "pnl_realized": self.pnl_realized,
            }, f, indent=2)

    # ── Market data (real NSE data via Yahoo Finance) ─────────
    def get_bars(self, symbol: str, period="60d", interval="1h") -> pd.DataFrame:
        """
        symbol: NSE symbol e.g. 'RELIANCE' (we add .NS automatically)
        interval: 1m,2m,5m,15m,30m,60m,1d
        """
        ticker = yf.Ticker(f"{symbol}.NS")
        df     = ticker.history(period=period, interval=interval)
        if df.empty:
            return pd.DataFrame()
        df.columns = df.columns.str.lower()
        df = df[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index)
        return df

    def get_latest_price(self, symbol: str) -> float:
        ticker = yf.Ticker(f"{symbol}.NS")
        data   = ticker.history(period="1d", interval="1m")
        if data.empty:
            return 0.0
        return float(data["Close"].iloc[-1])

    def is_market_open(self) -> bool:
        """NSE: Mon-Fri, 9:15 AM – 3:30 PM IST"""
        from pytz import timezone
        now = datetime.now(timezone("Asia/Kolkata"))
        if now.weekday() >= 5:  # Saturday/Sunday
            return False
        open_t  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
        close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return open_t <= now <= close_t

    # ── Paper order execution ─────────────────────────────────
    def place_order(self, symbol: str, qty: int, side: str,
                    stop_loss: float, take_profit: float) -> dict:
        price     = self.get_latest_price(symbol)
        cost      = price * qty
        # Simulate Zerodha brokerage: ₹20 flat or 0.03%, whichever lower
        brokerage = min(20, cost * 0.0003)

        if side.upper() == "BUY":
            if cost + brokerage > self.cash:
                return {"status": "REJECTED", "reason": "Insufficient paper capital"}
            self.cash -= (cost + brokerage)
            self.positions[symbol] = {
                "qty":       qty,
                "avg_entry": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "side":      "BUY",
                "timestamp": str(datetime.now()),
            }

        elif side.upper() == "SELL" and symbol in self.positions:
            pos   = self.positions.pop(symbol)
            pnl   = (price - pos["avg_entry"]) * pos["qty"] - brokerage
            self.cash         += (price * qty) - brokerage
            self.pnl_realized += pnl

        order = {
            "timestamp":   str(datetime.now()),
            "symbol":      symbol,
            "side":        side,
            "qty":         qty,
            "price":       price,
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "status":      "FILLED",
            "brokerage":   round(brokerage, 2),
        }
        self.order_log.append(order)
        self._save_state()
        return order

    def check_stops(self):
        """Check if any paper position hit SL or TP. Call every scan cycle."""
        exits = []
        for symbol, pos in list(self.positions.items()):
            price = self.get_latest_price(symbol)
            if price <= 0:
                continue
            if price <= pos["stop_loss"]:
                result = self.place_order(symbol, pos["qty"], "SELL",
                                          pos["stop_loss"], pos["take_profit"])
                exits.append({"symbol": symbol, "reason": "STOP_LOSS", "price": price})
            elif price >= pos["take_profit"]:
                result = self.place_order(symbol, pos["qty"], "SELL",
                                          pos["stop_loss"], pos["take_profit"])
                exits.append({"symbol": symbol, "reason": "TAKE_PROFIT", "price": price})
        return exits

    # ── Portfolio summary ─────────────────────────────────────
    def portfolio_summary(self) -> dict:
        unrealized = 0.0
        position_details = []
        for symbol, pos in self.positions.items():
            price     = self.get_latest_price(symbol)
            unreal_pl = (price - pos["avg_entry"]) * pos["qty"]
            unrealized += unreal_pl
            position_details.append({
                "symbol":    symbol,
                "qty":       pos["qty"],
                "avg_entry": pos["avg_entry"],
                "current":   price,
                "pnl":       round(unreal_pl, 2),
                "pnl_pct":   round((price - pos["avg_entry"]) / pos["avg_entry"] * 100, 2),
            })
        return {
            "cash":             round(self.cash, 2),
            "unrealized_pnl":   round(unrealized, 2),
            "realized_pnl":     round(self.pnl_realized, 2),
            "total_pnl":        round(self.pnl_realized + unrealized, 2),
            "open_positions":   len(self.positions),
            "positions":        position_details,
            "currency":         "INR",
        }
