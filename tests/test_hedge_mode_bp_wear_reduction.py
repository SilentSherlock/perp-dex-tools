import asyncio
import importlib
import sys
import types
from decimal import Decimal


def _load_hedgebot_class():
    lighter_pkg = types.ModuleType("lighter")
    signer_module = types.ModuleType("lighter.signer_client")

    class DummySignerClient:
        pass

    signer_module.SignerClient = DummySignerClient
    lighter_pkg.signer_client = signer_module
    sys.modules["lighter"] = lighter_pkg
    sys.modules["lighter.signer_client"] = signer_module

    backpack_module = types.ModuleType("exchanges.backpack")

    class DummyBackpackClient:
        pass

    backpack_module.BackpackClient = DummyBackpackClient
    sys.modules["exchanges.backpack"] = backpack_module

    module = importlib.import_module("hedge.hedge_mode_bp")
    return module.HedgeBot


class _DummyLogger:
    def __init__(self):
        self.messages = []

    def info(self, msg):
        self.messages.append(("info", str(msg)))

    def warning(self, msg):
        self.messages.append(("warning", str(msg)))

    def error(self, msg):
        self.messages.append(("error", str(msg)))


def _make_bot():
    hedge_bot_cls = _load_hedgebot_class()
    bot = hedge_bot_cls.__new__(hedge_bot_cls)
    bot.logger = _DummyLogger()
    bot.stop_flag = False
    bot.circuit_breaker_triggered = False
    bot.base_lighter_slippage = Decimal("0.0004")
    bot.max_lighter_slippage = Decimal("0.002")
    bot.tick_size = Decimal("0.01")
    bot.base_amount_multiplier = 1000
    bot.price_multiplier = 100
    bot.soft_exposure_limit = Decimal("1.5")
    bot.hard_exposure_limit = Decimal("2.0")
    bot.backpack_position = Decimal("0")
    bot.lighter_position = Decimal("0")
    bot.pending_lighter_hedges = []
    bot.waiting_for_lighter_fill = False
    return bot


def test_dynamic_slippage_is_capped_at_point_two_percent():
    bot = _make_bot()
    slippage = bot.compute_lighter_slippage(Decimal("100"), Decimal("101"))
    assert slippage == Decimal("0.002")


def test_normalize_lighter_order_params_applies_precision():
    bot = _make_bot()
    normalized_qty, normalized_price, base_amount, price_int = bot.normalize_lighter_order_params(
        Decimal("0.0014"), Decimal("101.237")
    )
    assert normalized_qty == Decimal("0.001")
    assert normalized_price == Decimal("101.24")
    assert base_amount == 1
    assert price_int == 10124


def test_check_exposure_limits_soft_limit_throttles(monkeypatch):
    bot = _make_bot()
    bot.backpack_position = Decimal("1.2")
    bot.lighter_position = Decimal("0.4")
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    result = asyncio.run(bot.check_exposure_limits())
    assert result is False
    assert sleep_calls == [1]
    assert bot.stop_flag is False


def test_check_exposure_limits_hard_limit_triggers_circuit_breaker():
    bot = _make_bot()
    bot.backpack_position = Decimal("2.2")
    bot.lighter_position = Decimal("0.2")

    try:
        asyncio.run(bot.check_exposure_limits())
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass

    assert bot.circuit_breaker_triggered is True
    assert bot.stop_flag is True


def test_process_pending_lighter_hedges_drains_queue():
    bot = _make_bot()
    called = []

    async def _fake_place(side, quantity, price):
        called.append((side, quantity, price))

    bot.place_lighter_market_order = _fake_place
    bot.pending_lighter_hedges = [
        {"lighter_side": "buy", "quantity": Decimal("0.1"), "price": Decimal("100")},
        {"lighter_side": "sell", "quantity": Decimal("0.2"), "price": Decimal("101")},
    ]

    asyncio.run(bot.process_pending_lighter_hedges())
    assert called == [
        ("buy", Decimal("0.1"), Decimal("100")),
        ("sell", Decimal("0.2"), Decimal("101")),
    ]
    assert bot.pending_lighter_hedges == []
    assert bot.waiting_for_lighter_fill is False
