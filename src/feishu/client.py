"""
飞书 API 客户端
处理与飞书 OpenAPI 的交互
使用 curl 作为 HTTP 客户端以绕过 Python DNS 问题
"""

import time
import json
import subprocess
from typing import Dict, Any, Optional


class FeishuClient:
    """飞书 OpenAPI 客户端"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        """
        初始化飞书客户端

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    def _curl_request(self, method: str, url: str, data: Dict[str, Any] = None,
                     headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        使用 curl 发送 HTTP 请求

        Args:
            method: HTTP 方法 (GET, POST, PUT, DELETE)
            url: 请求 URL
            data: 请求体数据
            headers: 请求头

        Returns:
            响应 JSON 数据
        """
        # 使用列表形式的命令（不使用 shell=True）
        cmd = ["curl", "-s", "-X", method, url]

        # 添加请求头
        if headers:
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])

        # 确保有 Content-Type
        if data and not any("Content-Type" in h for h in (headers or {})):
            cmd.extend(["-H", "Content-Type: application/json"])

        # 添加请求体
        if data:
            cmd.extend(["-d", json.dumps(data)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )

            # 检查返回状态
            if result.returncode != 0:
                error_msg = f"Curl failed with code {result.returncode}"
                if result.stderr:
                    error_msg += f", stderr: {result.stderr[:200]}"
                if result.stdout:
                    error_msg += f", stdout: {result.stdout[:200]}"
                raise Exception(error_msg)

            # 解析 JSON
            if not result.stdout.strip():
                raise Exception("Empty response from curl")

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            raise Exception("Curl request timed out")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {result.stdout}")

    def _get_access_token(self) -> str:
        """
        获取或刷新访问令牌

        Returns:
            访问令牌字符串
        """
        # 如果令牌仍然有效，直接返回
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        # 获取新的访问令牌
        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        data = self._curl_request("POST", url, data=payload)

        if data.get("code") != 0:
            raise Exception(f"Failed to get access token: {data.get('msg')}")

        self._access_token = data["tenant_access_token"]
        # 提前 5 分钟刷新
        self._token_expires_at = time.time() + data["expire"] - 300

        return self._access_token

    def send_card(self, receive_id: str, card: Dict[str, Any], receive_id_type: str = "open_id") -> str:
        """
        发送卡片消息给用户

        Args:
            receive_id: 接收者 ID（用户 open_id 或 user_id）
            card: 卡片 JSON 内容
            receive_id_type: ID 类型，默认 "open_id"

        Returns:
            message_id: 消息 ID

        Raises:
            Exception: 发送失败时抛出异常
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/im/v1/messages?receive_id_type={receive_id_type}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card)
        }

        data = self._curl_request("POST", url, data=payload, headers=headers)

        if data.get("code") != 0:
            raise Exception(f"Failed to send card: {data.get('msg')}")

        return data["data"]["message_id"]

    def update_card(self, message_id: str, card: Dict[str, Any]):
        """
        更新卡片消息

        Args:
            message_id: 消息 ID
            card: 新的卡片内容

        Raises:
            Exception: 更新失败时抛出异常
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/im/v1/messages/{message_id}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "msg_type": "interactive",
            "content": json.dumps(card)
        }

        data = self._curl_request("PUT", url, data=payload, headers=headers)

        if data.get("code") != 0:
            raise Exception(f"Failed to update card: {data.get('msg')}")

    def send_text(self, receive_id: str, text: str, receive_id_type: str = "open_id") -> str:
        """
        发送文本消息给用户

        Args:
            receive_id: 接收者 ID
            text: 文本内容
            receive_id_type: ID 类型

        Returns:
            message_id: 消息 ID
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/im/v1/messages?receive_id_type={receive_id_type}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }

        data = self._curl_request("POST", url, data=payload, headers=headers)

        if data.get("code") != 0:
            raise Exception(f"Failed to send text: {data.get('msg')}")

        return data["data"]["message_id"]


def create_client(config: Dict[str, Any]) -> FeishuClient:
    """
    从配置创建飞书客户端

    Args:
        config: 配置字典，包含 app_id 和 app_secret

    Returns:
        FeishuClient 实例

    Raises:
        ValueError: 配置缺失时抛出
    """
    app_id = config.get("app_id") or config.get("FEISHU_APP_ID")
    app_secret = config.get("app_secret") or config.get("FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        raise ValueError("Feishu app_id and app_secret are required")

    return FeishuClient(app_id, app_secret)
