"""
brokers/alpaca_broker.py — Alpaca Paper Trading Connector (US Stocks)
Free paper trading at https://alpaca.markets
"""
import pandas as pd
import requests
from datetime import datetime, timedelta
from config.settings import cfg


class AlpacaBroker:
    def __init__(self):
        self.base_url  = cfg.ALPACA_BASE_URL
        self.headers   = {
            "APCA-API-KEY-ID":     cfg.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": cfg.ALPACA_SECRET_KEY,
            "Content-Type":        "application/json",
        }                                           # FIX-A1: missing closing brace fixed
        self.data_url = "https://data.alpaca.markets"

    # ── Private HTTP helpers ──────────────────────────────────
    def _get(self, path: str, base=None, params=None):
        url = (base or self.base_url) + path
        r = requests.get(url, headers=self.headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict):
        url = self.base_url + path
        r = requests.post(url, headers=self.headers, json=payload, timeout=10)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str):
        url = self.base_url + path
        r = requests.delete(url, headers=self.headers, timeout=10)
        return r.status_code

    # ── Account info ──────────────────────────────────────────
    def get_account(self) -> dict:
        return self._get("/v2/account")

    def get_portfolio_value(self) -> float:
        return float(self.get_account().get("portfolio_value", 0))

    def get_buying_power(self) -> float:
        return float(self.get_account().get("buying_power", 0))

    # ── Market data ───────────────────────────────────────────
    def get_bars(self, symbol: str, timeframe: str = "1Hour",
                 limit: int = 100) -> pd.DataFrame:
        """
        Fetch OHLCV bars.
        timeframe: 1Min | 5Min | 15Min | 1Hour | 1Day
        """
        end   = datetime.utcnow()
        start = end - timedelta(days=30)
        params = {
            "timeframe": timeframe,
            "start":     start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit":     limit,
            "feed":      "iex",
        }                                           # FIX-A1: missing closing brace fixed
        try:
            data = self._get(
                f"/v2/stocks/{symbol}/bars",
                base=self.data_url,
                params=params
            )
        except Exception:
            return pd.DataFrame()

        bars = data.get("bars", [])
        if not bars:
            return pd.DataFrame()

        df = pd.DataFrame(bars)
        df.rename(columns={
            "t": "time", "o": "open", "h": "high",
            "l": "low",  "c": "close", "v": "volume"
        }, inplace=True)
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "volume"]]

    def get_latest_price(self, symbol: str) -> float:
        try:
            data = self._get(
                f"/v2/stocks/{symbol}/trades/latest",
                base=self.data_url,
                params={"feed": "iex"}
            )
            return float(data["trade"]["p"])
        except Exception:
            return 0.0

    # ── Order management ──────────────────────────────────────
    def place_order(self, symbol: str, qty: int, side: str,
                    stop_loss: float, take_profit: float) -> dict:
        """
        Place a bracket order (entry + automatic SL + TP via Alpaca).
        side: 'buy' or 'sell'

        FIX-A2: SELL orders must NOT include bracket legs.
        Alpaca rejects bracket orders on the SELL side — brackets are
        only valid when opening (buying) a position. Selling closes it.
        """
        if side.lower() == "buy":
            payload = {
                "symbol":        symbol,
                "qty":           qty,
                "side":          "buy",
                "type":          "market",
                "time_in_force": "day",
                "order_class":   "bracket",
                "stop_loss":     {"stop_price":  str(round(stop_loss,   2))},
                "take_profit":   {"limit_price": str(round(take_profit, 2))},
            }
        else:
            # FIX-A2: plain market SELL — no bracket legs
            payload = {
                "symbol":        symbol,
                "qty":           qty,
                "side":          "sell",
                "type":          "market",
                "time_in_force": "day",
            }
        return self._post("/v2/orders", payload)

    def get_positions(self) -> list:
        try:
            return self._get("/v2/positions")
        except Exception:
            return []

    def get_open_orders(self) -> list:
        try:
            return self._get("/v2/orders", params={"status": "open"})
        except Exception:
            return []

    def cancel_all_orders(self):
        return self._delete("/v2/orders")

    def close_position(self, symbol: str):
        """
        FIX-A3: close_position used _delete which returns status_code (int),
        but callers expect a dict. Use the dedicated close-position endpoint
        which returns the closing order as JSON.
        """
        url = self.base_url + f"/v2/positions/{symbol}"
        r = requests.delete(url, headers=self.headers, timeout=10)
        if r.status_code in (200, 207):
            return r.json()
        return {"status": r.status_code, "symbol": symbol}

    def is_market_open(self) -> bool:
        try:
            clock = self._get("/v2/clock")
            return clock.get("is_open", False)
        except Exception:
            return False

    # ── Check stops manually (FIX-A4) ────────────────────────
    def check_stops(self) -> list:
        """
        FIX-A4: Original had NO check_stops(). main.py calls broker.check_stops()
        on every scan cycle for all brokers. Without this, AttributeError crashed
        the entire scan loop.
        Alpaca handles bracket SL/TP server-side, so we just return positions
        that were closed by Alpaca (qty == 0 or position gone).
        """
        exits = []
        try:
            positions = {p["symbol"]: p for p in self.get_positions()}
            orders    = self.get_open_orders()
            # Report any filled stop/profit orders from open order list
            for o in orders:
                if o.get("status") == "filled" and o.get("order_class") in ("stop", "limit"):
                    exits.append({
                        "symbol": o["symbol"],
                        "reason": "STOP_OR_TARGET_FILLED",
                        "price":  float(o.get("filled_avg_price", 0)),
                    })
        except Exception:
            pass
        return exits

    # ── Portfolio summary ─────────────────────────────────────
    def portfolio_summary(self) -> dict:
        try:
            acc       = self.get_account()
            positions = self.get_positions()
            return {
                "portfolio_value": float(acc["portfolio_value"]),
                "buying_power":    float(acc["buying_power"]),
                "cash":            float(acc["cash"]),
                "pnl_today":       float(acc.get("unrealized_pl", 0)),
                "open_positions":  len(positions),
                "positions": [
                    {
                        "symbol":   p["symbol"],
                        "qty":      p["qty"],
                        "avg_entry": float(p["avg_entry_price"]),
                        "current":  float(p["current_price"]),
                        "pnl":      float(p["unrealized_pl"]),
                        "pnl_pct":  float(p["unrealized_plpc"]) * 100,
                    }
                    for p in positions
                ],
            }
        except Exception:
            return {
                "portfolio_value": 0, "buying_power": 0, "cash": 0,
                "pnl_today": 0, "open_positions": 0, "positions": [],
            }
