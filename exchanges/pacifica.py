import os
import asyncio
import json
import time
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
import aiohttp

from .base import BaseExchangeClient, OrderResult, OrderInfo, query_retry
from helpers.logger import TradingLogger
from .pacifica_signer import PacificaSigner


class PacificaWebSocketManager:
    """WebSocket manager for Pacifica market data and order updates."""

    def __init__(self, symbol: str,
                 price_callback=None,
                 bbo_callback=None,
                 orderbook_callback=None,
                 order_update_callback=None):
        self.symbol = symbol
        self.price_callback = price_callback
        self.bbo_callback = bbo_callback
        self.orderbook_callback = orderbook_callback
        self.order_update_callback = order_update_callback
        self.ws_url = "wss://ws.pacifica.fi"
        self.websocket = None
        self.running = False
        self.logger = None

    async def connect(self):
        """Connect and subscribe to Pacifica WebSocket streams."""
        while True:
            try:
                if self.logger:
                    self.logger.log(f"Connecting to Pacifica WebSocket for {self.symbol}", "INFO")
                self.websocket = await aiohttp.ClientSession().ws_connect(self.ws_url)
                self.running = True
                await self._subscribe()
                await self._listen()
            except Exception as e:
                if self.logger:
                    self.logger.log(f"WebSocket error: {e}", "ERROR")
                await asyncio.sleep(5)

    async def _subscribe(self):
        """Subscribe to price, BBO, orderbook, orders."""
        streams = [
            {"method": "subscribe", "params": {"source": "prices"}},
            {"method": "subscribe", "params": {"source": "bbo", "symbol": self.symbol}},
            {"method": "subscribe", "params": {"source": "book", "symbol": self.symbol, "agg_level": 1}},
            {"method": "subscribe", "params": {"source": "orders", "account": os.getenv("PACIFICA_ACCOUNT")}}
        ]
        for sub in streams:
            await self.websocket.send_str(json.dumps(sub))
            if self.logger:
                self.logger.log(f"Subscribed to {sub['params']['source']} for {self.symbol}", "INFO")

    async def _listen(self):
        """Listen for WebSocket messages."""
        async for msg in self.websocket:
            if not self.running:
                break
            try:
                data = json.loads(msg.data)
                await self._handle_message(data)
            except Exception as e:
                if self.logger:
                    self.logger.log(f"WebSocket message handling error: {e}", "ERROR")

    async def _handle_message(self, data: Dict[str, Any]):
        """Dispatch messages to correct callback."""
        channel = data.get("channel", "")
        payload = data.get("data", {})

        if channel == "prices" and self.price_callback:
            await self.price_callback(payload)
        elif channel == "bbo" and self.bbo_callback:
            await self.bbo_callback(payload)
        elif channel == "book" and self.orderbook_callback:
            await self.orderbook_callback(payload)
        elif channel == "orders" and self.order_update_callback:
            await self.order_update_callback(payload)
        else:
            if self.logger:
                self.logger.log(f"Unknown channel message: {channel} -> {payload}", "WARNING")

    async def disconnect(self):
        self.running = False
        if self.websocket:
            await self.websocket.close()
            if self.logger:
                self.logger.log("WebSocket disconnected", "INFO")

    def set_logger(self, logger):
        self.logger = logger


class PacificaClient(BaseExchangeClient):
    """Pacifica exchange client."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = "https://api.pacifica.fi"
        self.account = config.get("account", os.getenv("PACIFICA_ACCOUNT"))
        self.pacifica_private_key = config.get("private_key", os.getenv("PACIFICA_API_KEY"))
        if not self.account:
            raise ValueError("Pacifica account must be provided in config or env")
        self.logger = TradingLogger(exchange="pacifica", ticker=config.get("ticker", "UNKNOWN"))
        self.ws_manager: Optional[PacificaWebSocketManager] = None
        self.signer = PacificaSigner(self.pacifica_private_key)

    async def connect(self):
        self.ws_manager = PacificaWebSocketManager(
            symbol=self.config.ticker,
            price_callback=self._on_price,
            bbo_callback=self._on_bbo,
            orderbook_callback=self._on_orderbook,
            order_update_callback=self._on_order_update
        )
        self.ws_manager.set_logger(self.logger)
        asyncio.create_task(self.ws_manager.connect())
        await asyncio.sleep(1)

    async def disconnect(self):
        if self.ws_manager:
            await self.ws_manager.disconnect()

    def _get_headers(self) -> Dict[str, str]:
        return {"Accept": "*/*"}

    # --- WebSocket callbacks ---
    async def _on_price(self, data):
        # Example: {'symbol': 'BTC', 'mark': '105473', 'mid': '105476', ...}
        self.logger.log(f"[Price] {data['symbol']} mark: {data['mark']} mid: {data['mid']}", "DEBUG")

    async def _on_bbo(self, data):
        # Example: {'s': 'BTC', 'b': '87185', 'B': '1.234', 'a': '87186', 'A': '0.567'}
        self.logger.log(f"[BBO] {data['s']} bid: {data['b']} ask: {data['a']}", "DEBUG")

    async def _on_orderbook(self, data):
        # data['l'] = [bids, asks]
        self.logger.log(f"[Orderbook] {data['s']} bids: {data['l'][0]} asks: {data['l'][1]}", "DEBUG")

    async def _on_order_update(self, data):
        self.logger.log(f"[OrderUpdate] {data}", "INFO")

    # --- REST API methods ---
    @query_retry()
    async def get_active_orders(self) -> List[OrderInfo]:
        url = f"{self.base_url}/api/v1/orders?account={self.account}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._get_headers()) as resp:
                data = await resp.json()
        orders = []
        for o in data.get("data", []):
            orders.append(OrderInfo(
                order_id=o["order_id"],
                side=o["side"],
                size=Decimal(o["initial_amount"]),
                price=Decimal(o["price"]),
                status="OPEN",
                filled_size=Decimal(o["filled_amount"]),
                remaining_size=Decimal(o["initial_amount"]) - Decimal(o["filled_amount"])
            ))
        return orders

    async def place_limit_order(self, symbol: str, side: str, amount: Decimal, price: Optional[Decimal] = None) -> OrderResult:
        """Place a limit order with automatic client_order_id."""
        client_order_id = str(uuid.uuid4())
        if price is None:
            # Use simple BBO-based strategy: buy slightly below best ask / sell slightly above best bid
            bbo = await self.fetch_bbo(symbol)
            if side == "buy":
                price = bbo[1] - Decimal("0.01")
            else:
                price = bbo[0] + Decimal("0.01")

        url = f"{self.base_url}/api/v1/orders/create_limit"
        payload = {
            "account": self.account,
            "symbol": symbol,
            "side": side,
            "price": str(price),
            "initial_amount": str(amount),
            "client_order_id": client_order_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._get_headers(), json=payload) as resp:
                data = await resp.json()
        if data.get("success"):
            self.logger.log(f"[LimitOrder] Placed {side} {amount}@{price} with client_order_id={client_order_id}", "INFO")
            return OrderResult(success=True, order_id=data["data"]["order_id"], side=side, size=amount, price=price, status="NEW")
        self.logger.log(f"[LimitOrder] Failed: {data.get('error', 'Unknown')}", "ERROR")
        return OrderResult(success=False, error_message=data.get("error", "Unknown"))

    async def cancel_order(self, order_id: Optional[int] = None, client_order_id: Optional[str] = None) -> OrderResult:
        """Cancel an order and log."""
        url = f"{self.base_url}/api/v1/orders/cancel"
        payload = {"account": self.account}
        if order_id:
            payload["order_id"] = order_id
        if client_order_id:
            payload["client_order_id"] = client_order_id
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._get_headers(), json=payload) as resp:
                data = await resp.json()
        if data.get("success"):
            self.logger.log(f"[CancelOrder] Success order_id={order_id or client_order_id}", "INFO")
            return OrderResult(success=True)
        self.logger.log(f"[CancelOrder] Failed: {data.get('error', 'Unknown')}", "ERROR")
        return OrderResult(success=False, error_message=data.get("error", "Unknown"))

    @query_retry(default_return=(0, 0))
    async def fetch_bbo(self, symbol: str) -> Tuple[Decimal, Decimal]:
        """Fetch BBO prices (bid, ask) for a symbol."""
        url = f"{self.base_url}/api/v1/info"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._get_headers()) as resp:
                data = await resp.json()
        # Naive implementation: use tick info for now
        for m in data.get("data", []):
            if m["symbol"] == symbol:
                bid = Decimal(m.get("min_tick", "0"))
                ask = Decimal(m.get("max_tick", "0"))
                return bid, ask
        return Decimal("0"), Decimal("0")
