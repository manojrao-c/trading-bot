"""
brokers/binance_broker.py — Binance Testnet Broker
Paper trades crypto on Binance Testnet (zero real money).
Testnet URL: https://testnet.binance.vision
"""
import time
import hmac
import hashlib
import requests
import pandas as pd
from datetime import datetime
from config.settings import cfg


class BinanceBroker:
    BASE_URL = "https://testnet.binance.vision"  # Testnet — safe, no real money

    def __init__(self):
        self.api_key = cfg.BINANCE_API_KEY
        self.secret_key = cfg.BINANCE_SECRET_KEY
        self.positions = {}  # symbol -> {qty, entry, stop, target, side}
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    # ── Signed request helper ─────────────────────────────────
    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        params["signature"] = hmac.new(
            self.secret_key.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _get(self, path: str, params: dict = None, signed: bool = False):
        params = params or {}
        if signed:
            params = self._sign(params)
        r = self.session.get(f"{self.BASE_URL}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, params: dict):
        params = self._sign(params)
        r = self.session.post(f"{self.BASE_URL}{path}", params=params)
        r.raise_for_status()
        return r.json()

    # ── Market is always open (crypto = 24/7) ─────────────────
    def is_market_open(self) -> bool:
        return True

    # ── OHLCV bars via REST klines ────────────────────────────
    def get_bars(self, symbol: str, interval: str = "1h", limit: int = 100) -> pd.DataFrame:
        """
        Fetch OHLCV candles for a symbol.
        symbol   — e.g. "BTCUSDT", "ETHUSDT"
        interval — "1m","5m","15m","1h","4h","1d"
        """
        try:
            data = self._get("/api/v3/klines", {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            })
            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore"
            ])
            df = df[["open", "high", "low", "close", "volume"]].astype(float)
            return df
        except Exception:
            return pd.DataFrame()

    # ── Place a paper order on testnet ────────────────────────
    def place_order(self, symbol: str, qty: float, side: str,
                    stop_loss: float, take_profit: float) -> dict:
        """
        side: "BUY" or "SELL"
        BUY  → opens a long position and records it locally.
        SELL → closes the existing long position and removes it.
        Places a MARKET order on Binance Testnet.
        """
        order = self._post("/api/v3/order", {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty,
        })

        if side.upper() == "BUY":
            # Record the new long position
            entry = (
                float(order.get("fills", [{}])[0].get("price", 0))
                or self._last_price(symbol)
            )
            self.positions[symbol] = {
                "qty": qty,
                "entry": entry,
                "stop": stop_loss,
                "target": take_profit,
                "side": "BUY",
                "time": datetime.now().isoformat(),
            }
        else:
            # SELL closes the long — remove from tracked positions
            self.positions.pop(symbol, None)

        return order

    def _last_price(self, symbol: str) -> float:
        try:
            data = self._get("/api/v3/ticker/price", {"symbol": symbol})
            return float(data["price"])
        except Exception:
            return 0.0

    # ── Check stops & targets for open positions ──────────────
    def check_stops(self) -> list:
        """
        Returns list of exits: [{symbol, reason, price}]
        Long-only agent — only checks long (BUY) exits.
        """
        exits = []
        for symbol, pos in list(self.positions.items()):
            price = self._last_price(symbol)
            if price == 0:
                continue
            reason = None
            if price <= pos["stop"]:
                reason = "STOP_LOSS"
            elif price >= pos["target"]:
                reason = "TAKE_PROFIT"
            if reason:
                exits.append({"symbol": symbol, "reason": reason, "price": price})
                del self.positions[symbol]
        return exits

    # ── Portfolio summary ─────────────────────────────────────
    def portfolio_summary(self) -> dict:
        try:
            account = self._get("/api/v3/account", signed=True)
            usdt = next(
                (float(b["free"]) + float(b["locked"])
                 for b in account.get("balances", [])
                 if b["asset"] == "USDT"),
                0.0
            )
            # Compute unrealized P&L from open positions
            unrealized = 0.0
            for symbol, pos in self.positions.items():
                price = self._last_price(symbol)
                if price > 0:
                    unrealized += (price - pos["entry"]) * pos["qty"]

            return {
                "portfolio_value": round(usdt, 2),
                "cash": round(usdt, 2),
                "unrealized_pnl": round(unrealized, 2),
                "positions": len(self.positions),
                "currency": "USDT",
            }
        except Exception:
            return {
                "portfolio_value": 0, "cash": 0,
                "unrealized_pnl": 0, "positions": 0, "currency": "USDT"
            }
