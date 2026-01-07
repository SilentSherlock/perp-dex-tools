import time
import json
import base58
from solders.keypair import Keypair

class PacificaSigner:
    """
    Pacifica.fi 交易签名器
    封装了递归排序、规范化 JSON 生成及 Ed25519 签名逻辑。
    """
    def __init__(self, private_key_base58: str, expiry_window: int = 30_000):
        """
        初始化签名器
        :param private_key_base58: Base58 格式的私钥字符串
        :param expiry_window: 签名有效期（毫秒），默认 30 秒
        """
        # 从私钥生成 Keypair
        self.keypair = Keypair.from_bytes(base58.b58decode(private_key_base58))
        self.public_key = str(self.keypair.pubkey())
        self.expiry_window = expiry_window

    def _sort_json_keys(self, value):
        """递归对所有 JSON 键进行字母排序"""
        if isinstance(value, dict):
            return {k: self._sort_json_keys(value[k]) for k in sorted(value.keys())}
        elif isinstance(value, list):
            return [self._sort_json_keys(item) for item in value]
        else:
            return value

    def sign_operation(self, operation_type: str, operation_data: dict) -> dict:
        """
        对操作进行签名并返回完整的请求载荷
        :param operation_type: 操作类型 (例如 'create_order', 'cancel_order')
        :param operation_data: 该操作对应的原始业务参数字典
        :return: 包含签名和账户信息的最终请求字典
        """
        timestamp = int(time.time() * 1_000)

        # 1. 构建待签名头部
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": self.expiry_window,
            "type": operation_type,
        }

        # 2. 合并数据用于签名 (根据文档：数据需在 data 字段下)
        data_to_sign = {
            **signature_header,
            "data": operation_data,
        }

        # 3. 递归排序并生成紧凑 JSON 字符串
        sorted_message = self._sort_json_keys(data_to_sign)
        compact_json = json.dumps(sorted_message, separators=(",", ":"))

        # 4. 执行签名
        message_bytes = compact_json.encode("utf-8")
        signature = self.keypair.sign_message(message_bytes)
        signature_b58 = base58.b58encode(bytes(signature)).decode("ascii")

        # 5. 构建最终请求格式 (根据文档：业务字段需与 Header 平级展开)
        request_header = {
            "account": self.public_key,
            "agent_wallet": None,  # 如有代理钱包需求可在此扩展
            "signature": signature_b58,
            "timestamp": timestamp,
            "expiry_window": self.expiry_window,
        }

        return {
            **request_header,
            **operation_data,
        }
