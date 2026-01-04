import time
import json
import base58
from typing import Dict, Any
from solders.keypair import Keypair


class PacificaSigner:
    """
    Pacifica request signer
    """

    def __init__(self, private_key_b58: str):
        self.keypair = Keypair.from_bytes(base58.b58decode(private_key_b58))
        self.public_key = str(self.keypair.pubkey())

    @staticmethod
    def _sort_json_keys(value):
        if isinstance(value, dict):
            return {k: PacificaSigner._sort_json_keys(value[k]) for k in sorted(value)}
        elif isinstance(value, list):
            return [PacificaSigner._sort_json_keys(v) for v in value]
        return value

    def sign(
            self,
            operation_type: str,
            operation_data: Dict[str, Any],
            expiry_window: int = 5_000,
    ) -> Dict[str, Any]:
        """
        Generate signed request payload
        """

        timestamp = int(time.time() * 1000)

        sign_payload = {
            "timestamp": timestamp,
            "expiry_window": expiry_window,
            "type": operation_type,
            "data": operation_data,
        }

        # 递归排序
        sorted_payload = self._sort_json_keys(sign_payload)

        # 紧凑 JSON
        compact_json = json.dumps(sorted_payload, separators=(",", ":"))

        # 签名
        signature = self.keypair.sign_message(compact_json.encode("utf-8"))
        signature_b58 = base58.b58encode(bytes(signature)).decode("ascii")

        # 返回最终 header + 原始 data（不是 data wrapper）
        return {
            "account": self.public_key,
            "agent_wallet": None,
            "signature": signature_b58,
            "timestamp": timestamp,
            "expiry_window": expiry_window,
            **operation_data,
        }
