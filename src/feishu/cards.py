"""
飞书消息卡片构建器
创建交互式卡片用于权限请求
"""

import json
from typing import Dict, Any


class CardBuilder:
    """构建飞书交互式卡片"""

    def build_permission_card(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        request_id: str
    ) -> Dict[str, Any]:
        """
        构建权限请求卡片

        Args:
            tool_name: 工具名称（如 Bash, WebSearch）
            tool_input: 工具输入参数
            request_id: 唯一请求 ID

        Returns:
            卡片 JSON
        """
        # 格式化工具输入显示
        input_text = self._format_tool_input(tool_name, tool_input)

        # 根据工具类型设置图标
        icon = self._get_tool_icon(tool_name)

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{icon} Claude Code 权限请求"
                },
                "template": "yellow"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**工具**: `{tool_name}`\n\n**参数**:\n```json\n{input_text}\n```"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "允许"
                            },
                            "type": "primary",
                            "value": {
                                "request_id": request_id,
                                "behavior": "allow"
                            }
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "拒绝"
                            },
                            "type": "danger",
                            "value": {
                                "request_id": request_id,
                                "behavior": "deny"
                            }
                        }
                    ]
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"ID: {request_id[:8]}...",
                        "extra": {
                            "style": {
                                "font_size": "small",
                                "color": "grey"
                            }
                        }
                    }
                }
            ]
        }

        return card

    def build_result_card(self, decision: Dict[str, Any], tool_name: str = "") -> Dict[str, Any]:
        """
        构建结果展示卡片

        Args:
            decision: 决策结果 {"behavior": "allow|deny", "message": "..."}
            tool_name: 工具名称（可选）

        Returns:
            卡片 JSON
        """
        behavior = decision.get("behavior")
        message = decision.get("message", "")

        if behavior == "allow":
            title = "已允许"
            template = "green"
            icon = ""
        else:
            title = "已拒绝"
            template = "red"
            icon = ""

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{icon} {title}"
                },
                "template": template
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"{icon} {message}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": "此请求已处理",
                        "extra": {
                            "style": {
                                "font_size": "small",
                                "color": "grey"
                            }
                        }
                    }
                }
            ]
        }

        return card

    def build_error_card(self, error_message: str) -> Dict[str, Any]:
        """
        构建错误卡片

        Args:
            error_message: 错误消息

        Returns:
            卡片 JSON
        """
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": " 错误"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": error_message
                    }
                }
            ]
        }

        return card

    def _format_tool_input(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        格式化工具输入为可读文本

        Args:
            tool_name: 工具名称
            tool_input: 工具输入

        Returns:
            格式化后的字符串
        """
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            description = tool_input.get("description", "")
            if description:
                return f"{command}\n# {description}"
            return command
        elif tool_name == "Edit":
            path = tool_input.get("file_path", "")
            old_str = tool_input.get("old_string", "")[:50]
            new_str = tool_input.get("new_string", "")[:50]
            return f"文件: {path}\n替换: {old_str}... -> {new_str}..."
        elif tool_name == "Write":
            path = tool_input.get("file_path", "")
            return f"文件: {path}"
        elif tool_name == "WebFetch" or tool_name == "WebSearch":
            url = tool_input.get("url", "")
            query = tool_input.get("query", "")
            return f"URL: {url}" if url else f"查询: {query}"
        else:
            # 默认 JSON 格式
            return json.dumps(tool_input, indent=2, ensure_ascii=False)[:500]

    def _get_tool_icon(self, tool_name: str) -> str:
        """
        获取工具图标

        Args:
            tool_name: 工具名称

        Returns:
            图标 emoji
        """
        icons = {
            "Bash": "",
            "Edit": "",
            "Write": "",
            "Read": "",
            "WebFetch": "",
            "WebSearch": "",
            "AskUserQuestion": "",
            "Glob": "",
            "Grep": ""
        }
        return icons.get(tool_name, "")


def parse_card_action(action_value: str) -> Dict[str, Any]:
    """
    解析卡片操作值

    Args:
        action_value: JSON 字符串

    Returns:
        解析后的字典，包含 request_id 和 behavior
    """
    try:
        return json.loads(action_value)
    except json.JSONDecodeError:
        return {"request_id": "", "behavior": ""}
