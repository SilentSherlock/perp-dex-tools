import asyncio
from decimal import Decimal
from exchanges.pacifica import PacificaClient


async def test_pacifica_client():
    # 配置
    config = {
        "ticker": "BTC",
        "account": "",   # 默认使用环境变量 PACIFICA_ACCOUNT
        "quantity": Decimal("0.001"),
    }

    # 初始化客户端
    client = PacificaClient(config)

    # 连接 WebSocket
    await client.connect()

    # 等待几秒接收 WebSocket 回调消息
    print("等待 5 秒接收 WebSocket 事件...")
    await asyncio.sleep(5)

    # 测试获取 BBO
    bid, ask = await client.fetch_bbo("BTC")
    print(f"BBO: bid={bid}, ask={ask}")

    # 测试限价单下单（自动生成 client_order_id）
    print("下单测试: 买入限价单 0.001 BTC")
    order_result = await client.place_limit_order("BTC", side="buy", amount=Decimal("0.001"))
    print(f"下单结果: {order_result}")

    # 获取当前活跃订单
    orders = await client.get_active_orders()
    print(f"活跃订单数: {len(orders)}")
    for o in orders:
        print(f"订单: id={o.order_id}, side={o.side}, size={o.size}, price={o.price}, status={o.status}")

    # 测试撤单
    if orders:
        first_order_id = orders[0].order_id
        print(f"撤单测试: order_id={first_order_id}")
        cancel_result = await client.cancel_order(order_id=first_order_id)
        print(f"撤单结果: {cancel_result}")

    # 断开 WebSocket
    await client.disconnect()
    print("客户端测试完成")


if __name__ == "__main__":
    asyncio.run(test_pacifica_client())
