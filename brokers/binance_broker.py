"""
brokers/binance_broker.py — Binance Testnet Broker
Paper trades crypto on Binance Testnet (zero real money).
Testnet URL: https://testnet.binance.vision
"""
import time, hmac, hashlib, math
import requests
import pandas as pd
from datetime import datetime
from config.settings import cfg

class BinanceBroker:
    BASE_URL = "https://testnet.binance.vision"

    def __init__(self):
        self.api_key    = cfg.BINANCE_API_KEY
        self.secret_key = cfg.BINANCE_SECRET_KEY
        self.positions  = {}   # symbol -> {qty, entry, stop, target, side}
        self._lot_cache = {}   # symbol -> step_size (cached)
        self.session    = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    # ── Signed request helpers ────────────────────────────────
    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        params["signature"] = hmac.new(
            self.secret_key.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _get(self, path: str, params: dict | None = None, signed: bool = False):
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

    # ── Lot size helper — fetches step_size from exchange info ─
    def _lot_step(self, symbol: str) -> float:
        """Returns the LOT_SIZE stepSize for a symbol (cached)."""
        if symbol in self._lot_cache:
            return self._lot_cache[symbol]
        try:
            info = self._get("/api/v3/exchangeInfo", {"symbol": symbol})
            for f in info["symbols"][0]["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step = float(f["stepSize"])
                    self._lot_cache[symbol] = step
                    return step
        except Exception:
            pass
        return 1.0  # safe fallback

    def _round_qty(self, symbol: str, qty: float) -> float:
        """Round qty down to the nearest valid step size."""
        step = self._lot_step(symbol)
        precision = max(0, round(-math.log10(step)))
        rounded = math.floor(qty / step) * step
        return round(rounded, precision)

    # ── Market is always open (crypto = 24/7) ─────────────────
    def is_market_open(self) -> bool:
        return True

    # ── OHLCV bars via REST klines ─────────────────────────────
    def get_bars(self, symbol: str, interval: str = "1h", limit: int = 100) -> pd.DataFrame:
        try:
            data = self._get("/api/v3/klines", {
                "symbol": symbol, "interval": interval, "limit": limit,
            })
            df = pd.DataFrame(data, columns=[
                "open_time","open","high","low","close","volume",
                "close_time","quote_vol","trades","taker_base","taker_quote","ignore"
            ])
            df = df[["open","high","low","close","volume"]].astype(float)
            return df
        except Exception:
            return pd.DataFrame()

    # ── Place order — qty rounded to correct step size ─────────
    def place_order(self, symbol: str, qty: float, side: str,
                    stop_loss: float, take_profit: float) -> dict:
        """
        side: "BUY" or "SELL"
        Rounds qty to Binance LOT_SIZE before submitting.
        """
        qty = self._round_qty(symbol, qty)

        if qty <= 0:
            raise ValueError(f"Qty rounded to 0 for {symbol} — position too small")

        order = self._post("/api/v3/order", {
            "symbol":   symbol,
            "side":     side.upper(),
            "type":     "MARKET",
            "quantity": qty,
        })

        fills = order.get("fills", [])
        entry = float(fills[0]["price"]) if fills else self._last_price(symbol)

        self.positions[symbol] = {
            "qty":    qty,
            "entry":  entry,
            "stop":   stop_loss,
            "target": take_profit,
            "side":   side.upper(),
            "time":   datetime.now().isoformat(),
        }
        return order

    def _last_price(self, symbol: str) -> float:
        try:
            data = self._get("/api/v3/ticker/price", {"symbol": symbol})
            return float(data["price"])
        except Exception:
            return 0.0

    # ── Check stops & targets ─────────────────────────────────
    def check_stops(self) -> list:
        """Returns list of exits: [{symbol, reason, price}]"""
        exits = []
        for symbol, pos in list(self.positions.items()):
            price = self._last_price(symbol)
            if price == 0:
                continue

            reason = None

            # ── Price-based exits ─────────────────────────────
            if pos["side"] == "BUY":
                if price <= pos["stop"]:     reason = "STOP_LOSS"
                elif price >= pos["target"]: reason = "TAKE_PROFIT"
            else:  # SELL / SHORT
                if price >= pos["stop"]:     reason = "STOP_LOSS"
                elif price <= pos["target"]: reason = "TAKE_PROFIT"

            # ── Time-based exit (24h max hold) ────────────────
            if not reason:
                try:
                    entry_time = datetime.fromisoformat(pos["time"])
                    hours_held = (datetime.now() - entry_time).total_seconds() / 3600
                    if hours_held >= 24:
                        reason = f"TIME_EXIT ({hours_held:.1f}h)"
                except Exception:
                    pass

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
                 if b["asset"] == "USDT"), 0.0
            )
            return {
                "portfolio_value": round(usdt, 2),
                "cash":            round(usdt, 2),
                "positions":       len(self.positions),
                "positions_list":  [],
                "currency":        "USDT",
            }
        except Exception:
            return {"portfolio_value": 0, "cash": 0, "positions": 0,
                    "positions_list": [], "currency": "USDT"}
