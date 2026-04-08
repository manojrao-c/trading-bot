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
        self.base_url = cfg.ALPACA_BASE_URL
        self.headers  = {
            "APCA-API-KEY-ID":     cfg.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": cfg.ALPACA_SECRET_KEY,
            "Content-Type":        "application/json",
        }
        self.data_url = "https://data.alpaca.markets"

    def _get(self, path: str, base=None, params=None):
        url = (base or self.base_url) + path
        r   = requests.get(url, headers=self.headers, params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict):
        url = self.base_url + path
        r   = requests.post(url, headers=self.headers, json=payload)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str):
        url = self.base_url + path
        r   = requests.delete(url, headers=self.headers)
        return r.status_code

    # ── Account info ─────────────────────────────────────────
    def get_account(self) -> dict:
        return self._get("/v2/account")

    def get_portfolio_value(self) -> float:
        acc = self.get_account()
        return float(acc.get("portfolio_value", 0))

    def get_buying_power(self) -> float:
        acc = self.get_account()
        return float(acc.get("buying_power", 0))

    # ── Market data ───────────────────────────────────────────
    def get_bars(self, symbol: str, timeframe="1Hour", limit=100) -> pd.DataFrame:
        """Fetch OHLCV bars. timeframe: 1Min, 5Min, 15Min, 1Hour, 1Day"""
        end   = datetime.utcnow()
        start = end - timedelta(days=30)
        params = {
            "timeframe": timeframe,
            "start":     start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit":     limit,
            "feed":      "iex",
        }
        data = self._get(f"/v2/stocks/{symbol}/bars", base=self.data_url, params=params)
        bars = data.get("bars", [])
        if not bars:
            return pd.DataFrame()
        df = pd.DataFrame(bars)
        df.rename(columns={"t": "time", "o": "open", "h": "high",
                           "l": "low",  "c": "close","v": "volume"}, inplace=True)
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "volume"]]

    def get_latest_price(self, symbol: str) -> float:
        data = self._get(f"/v2/stocks/{symbol}/trades/latest",
                         base=self.data_url, params={"feed": "iex"})
        return float(data["trade"]["p"])

    # ── Order management ──────────────────────────────────────
    def place_order(self, symbol: str, qty: int, side: str,
                    stop_loss: float, take_profit: float) -> dict:
        """
        Place a bracket order (entry + automatic SL + TP).
        side: 'buy' or 'sell'
        """
        payload = {
            "symbol":        symbol,
            "qty":           qty,
            "side":          side,
            "type":          "market",
            "time_in_force": "day",
            "order_class":   "bracket",
            "stop_loss":     {"stop_price": str(round(stop_loss, 2))},
            "take_profit":   {"limit_price": str(round(take_profit, 2))},
        }
        return self._post("/v2/orders", payload)

    def get_positions(self) -> list:
        return self._get("/v2/positions")

    def get_open_orders(self) -> list:
        return self._get("/v2/orders", params={"status": "open"})

    def cancel_all_orders(self):
        return self._delete("/v2/orders")

    def close_position(self, symbol: str) -> dict:
        return self._delete(f"/v2/positions/{symbol}")

    def is_market_open(self) -> bool:
        clock = self._get("/v2/clock")
        return clock.get("is_open", False)

    # ── Portfolio summary ─────────────────────────────────────
    def portfolio_summary(self) -> dict:
        acc       = self.get_account()
        positions = self.get_positions()
        return {
            "portfolio_value": float(acc["portfolio_value"]),
            "buying_power":    float(acc["buying_power"]),
            "cash":            float(acc["cash"]),
            "pnl_today":       float(acc.get("unrealized_pl", 0)),
            "open_positions":  len(positions),
            "positions":       [
                {
                    "symbol":     p["symbol"],
                    "qty":        p["qty"],
                    "avg_entry":  float(p["avg_entry_price"]),
                    "current":    float(p["current_price"]),
                    "pnl":        float(p["unrealized_pl"]),
                    "pnl_pct":    float(p["unrealized_plpc"]) * 100,
                }
                for p in positions
            ],
        }
