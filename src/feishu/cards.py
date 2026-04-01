"""
飞书消息卡片构建器
创建交互式卡片用于权限请求
"""

import json
from typing import Dict, Any, List


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

    # ==================== AskUserQuestion 卡片方法 ====================

    def build_question_card(
        self,
        questions: List[Dict[str, Any]],
        request_id: str
    ) -> Dict[str, Any]:
        """
        构建问题收集卡片

        Args:
            questions: 问题列表，每个问题包含:
                - question_id: 唯一标识
                - question_text: 问题内容
                - question_type: "text" | "select" | "multi_select"
                - options: 选项列表(select/multi_select 时有值)
            request_id: 请求 ID

        Returns:
            飞书卡片 JSON
        """
        elements = []

        # 添加问题元素
        for i, q in enumerate(questions):
            question_id = q["question_id"]
            question_text = q["question_text"]
            question_type = q.get("question_type", "text")

            # 问题标题
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**问题 {i+1}**:\n{question_text}"
                }
            })

            # 根据类型添加输入元素
            if question_type == "text":
                # 文本输入：提示用户在飞书中直接回复
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "*请在飞书中直接回复您的答案*"
                    }
                })
            elif question_type == "select":
                # 单选：使用多个按钮
                options = q.get("options", [])
                buttons = []
                for opt in options:
                    buttons.append({
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": opt
                        },
                        "type": "default",
                        "value": {
                            "request_id": request_id,
                            "action": "answer",
                            "question_id": question_id,
                            "answer": opt
                        }
                    })

                # 将按钮添加到元素中（每行最多3个按钮）
                for i in range(0, len(buttons), 3):
                    elements.append({
                        "tag": "action",
                        "actions": buttons[i:i+3]
                    })
            elif question_type == "multi_select":
                # 多选：提示用户回复逗号分隔的选项
                options = q.get("options", [])
                options_text = "、".join(options)

                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"*可选项*: {options_text}\n\n*请在飞书中直接回复您选择的选项（多个选项用逗号分隔）*"
                    }
                })

        # 只添加取消按钮（选择问题不需要提交按钮）
        elements.append({"tag": "hr"})
        cancel_actions = [
            {
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": "取消"
                },
                "type": "default",
                "value": {
                    "request_id": request_id,
                    "action": "cancel"
                }
            }
        ]

        # 对于文本输入问题，添加"跳过"按钮
        has_text_question = any(q.get("question_type") == "text" for q in questions)
        if has_text_question:
            cancel_actions.insert(0, {
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": "跳过此问题"
                },
                "type": "default",
                "value": {
                    "request_id": request_id,
                    "action": "skip"
                }
            })

        elements.append({
            "tag": "action",
            "actions": cancel_actions
        })

        # 添加 ID 显示
        elements.append({
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
        })

        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": " Claude Code 需要您的反馈"
                },
                "template": "blue"
            },
            "elements": elements
        }

        return card

    def build_question_result_card(
        self,
        answers: Dict[str, str],
        status: str
    ) -> Dict[str, Any]:
        """
        构建问题回答结果卡片

        Args:
            answers: 问题答案字典 {question_id: answer}
            status: 状态 (success/timeout/cancel)

        Returns:
            卡片 JSON
        """
        if status == "success":
            title = "已收到您的回答"
            template = "green"
            icon = ""
        elif status == "timeout":
            title = "等待超时"
            template = "yellow"
            icon = ""
        else:  # cancel
            title = "已取消"
            template = "grey"
            icon = ""

        # 构建答案显示
        answer_elements = []
        for q_id, answer in answers.items():
            answer_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{q_id}**: {answer}"
                }
            })

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
                        "content": "您的回答已传递给 Claude Code"
                    }
                }
            ]
        }

        # 如果有答案，显示答案
        if answer_elements:
            card["elements"].append({"tag": "hr"})
            card["elements"].extend(answer_elements)

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
