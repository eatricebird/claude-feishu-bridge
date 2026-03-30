#!/usr/bin/env python3
"""
Claude Code PermissionRequest Hook
拦截权限请求并通过飞书发送通知，等待用户响应

输入格式（通过 stdin）：
{
    "session_id": "abc123",
    "tool_name": "Bash",
    "tool_input": {
        "command": "rm -rf node_modules",
        "description": "Remove node_modules directory"
    },
    "permission_suggestions": [...]
}

输出格式（通过 stdout）：
{
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {
            "behavior": "allow|deny",
            "message": "原因说明"
        }
    }
}
"""

import sys
import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import PermissionStorage
from src.feishu.client import FeishuClient
from src.feishu.cards import CardBuilder


def load_config():
    """加载配置文件"""
    import yaml

    config_path = PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "deny",
                    "message": "配置文件不存在，请先创建 config/config.yaml"
                }
            }
        }))
        sys.exit(0)

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class PermissionHook:
    """权限请求 Hook 处理器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.storage = PermissionStorage(
            config.get("storage", {}).get("path", "./data/permissions.json")
        )
        self.card_builder = CardBuilder()

        # 初始化飞书客户端
        feishu_config = config.get("feishu", {})
        app_id = feishu_config.get("app_id") or os.getenv("FEISHU_APP_ID")
        app_secret = feishu_config.get("app_secret") or os.getenv("FEISHU_APP_SECRET")
        self.user_id = feishu_config.get("user_id") or os.getenv("FEISHU_USER_ID")

        if not app_id or not app_secret:
            raise ValueError("飞书 app_id 和 app_secret 配置缺失")

        self.feishu = FeishuClient(app_id, app_secret)

        # 权限请求配置
        perm_config = config.get("permissions", {})
        self.timeout = perm_config.get("timeout", 300)
        self.poll_interval = perm_config.get("poll_interval", 2)

    def handle_permission_request(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理权限请求
        """
        # 生成唯一请求 ID
        request_id = str(uuid.uuid4())
        session_id = input_data.get("session_id", "")
        tool_name = input_data.get("tool_name", "Unknown")
        tool_input = input_data.get("tool_input", {})

        # 构建权限请求数据
        permission_data = {
            "request_id": request_id,
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "status": "pending",
            "created_at": time.time(),
            "updated_at": time.time()
        }

        # 保存到存储
        self.storage.save_request(request_id, permission_data)

        # 构建并发送飞书消息卡片
        card = self.card_builder.build_permission_card(
            tool_name=tool_name,
            tool_input=tool_input,
            request_id=request_id
        )

        try:
            message_id = self.feishu.send_card(
                receive_id=self.user_id,
                card=card
            )

            # 更新存储中的消息 ID
            permission_data["feishu_message_id"] = message_id
            self.storage.save_request(request_id, permission_data)

            # 等待用户响应
            decision = self._wait_for_decision(request_id)

            # 更新飞书消息卡片显示决策结果
            try:
                result_card = self.card_builder.build_result_card(decision, tool_name)
                self.feishu.update_card(message_id, result_card)
            except Exception as e:
                # 更新卡片失败不影响主流程
                print(f"Warning: Failed to update card: {e}", file=sys.stderr)

            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": decision
                }
            }

        except Exception as e:
            # 发送失败时回退到拒绝
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": f"飞书通知发送失败: {str(e)}"
                    }
                }
            }

    def _wait_for_decision(self, request_id: str) -> Dict[str, Any]:
        """
        等待用户决策（轮询模式）

        Args:
            request_id: 请求 ID

        Returns:
            决策结果 {"behavior": "allow|deny", "message": "..."}
        """
        start_time = time.time()

        while (time.time() - start_time) < self.timeout:
            request_data = self.storage.get_request(request_id)

            if request_data and request_data.get("status") in ["allow", "deny"]:
                # 用户已响应
                behavior = request_data["status"]
                return {
                    "behavior": behavior,
                    "message": request_data.get("user_message", "")
                }

            time.sleep(self.poll_interval)

        # 超时
        return {
            "behavior": "deny",
            "message": f"等待用户响应超时（{self.timeout}秒）"
        }


def main():
    """Hook 入口点"""
    try:
        # 加载配置
        config = load_config()

        # 从 stdin 读取输入
        input_data = json.load(sys.stdin)

        # 处理权限请求
        hook = PermissionHook(config)
        result = hook.handle_permission_request(input_data)

        # 输出结果
        print(json.dumps(result))
        sys.exit(0)

    except ValueError as e:
        # 配置错误
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "deny",
                    "message": str(e)
                }
            }
        }))
        sys.exit(0)

    except Exception as e:
        # 其他错误
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "deny",
                    "message": f"Hook 执行失败: {str(e)}"
                }
            }
        }))
        sys.exit(0)


if __name__ == "__main__":
    main()
