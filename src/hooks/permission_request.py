#!/usr/bin/env python3
"""
Claude Code PermissionRequest Hook
拦截权限请求并通过飞书发送通知，等待用户响应

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

# 日志文件路径
LOG_FILE = Path(__file__).parent.parent.parent / "data" / "hook_debug.log"

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

        # AskUserQuestion 远程模式配置
        question_config = config.get("ask_user_question", {})
        self.question_timeout = min(
            question_config.get("timeout", 300),
            self.timeout - 10  # 留余量，不超过 hook 总超时
        )

    def handle_permission_request(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理权限请求
        """
        tool_name = input_data.get("tool_name", "Unknown")

        if tool_name == "AskUserQuestion":
            # 发送飞书交互卡片，阻塞等回答，返回 allow
            return self._handle_ask_user_question(input_data)

        # 其他工具：发送权限卡片，等待 allow/deny
        return self._handle_tool_permission(input_data)

    def _handle_tool_permission(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理普通工具的权限请求"""
        request_id = str(uuid.uuid4())
        tool_name = input_data.get("tool_name", "Unknown")
        tool_input = input_data.get("tool_input", {})

        permission_data = {
            "request_id": request_id,
            "session_id": input_data.get("session_id", ""),
            "tool_name": tool_name,
            "tool_input": tool_input,
            "status": "pending",
            "created_at": time.time(),
            "updated_at": time.time()
        }

        self.storage.save_request(request_id, permission_data)

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

            permission_data["feishu_message_id"] = message_id
            self.storage.save_request(request_id, permission_data)

            decision = self._wait_for_decision(request_id)

            try:
                result_card = self.card_builder.build_result_card(decision, tool_name)
                self.feishu.update_card(message_id, result_card)
            except Exception as e:
                print(f"Warning: Failed to update card: {e}", file=sys.stderr)

            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": decision
                }
            }

        except Exception as e:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": f"飞书通知发送失败: {str(e)}"
                    }
                }
            }

    def _handle_ask_user_question(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 AskUserQuestion：
        发送飞书交互卡片，阻塞等待回答，写入 data/last_answer.json。
        终端选择框和飞书卡片同时显示，用户可从任一端回答。
        飞书回答写入文件，Claude 通过 CLAUDE.md 指令读取。
        """
        tool_input = input_data.get("tool_input", {})
        questions = self._parse_questions(tool_input)

        if not questions:
            return self._make_decision("allow", "")

        log_debug(f"AskUserQuestion remote: {len(questions)} questions, sending to Feishu")

        # 保存请求
        request_id = str(uuid.uuid4())
        question_data = {
            "request_id": request_id,
            "session_id": input_data.get("session_id", ""),
            "hook_event_name": "AskUserQuestion",
            "questions": questions,
            "status": "pending",
            "created_at": time.time(),
            "updated_at": time.time()
        }
        self.storage.save_request(request_id, question_data)

        # 发送飞书交互卡片
        try:
            card = self.card_builder.build_question_card(
                questions=questions,
                request_id=request_id
            )
            message_id = self.feishu.send_card(receive_id=self.user_id, card=card)
            question_data["feishu_message_id"] = message_id
            self.storage.save_request(request_id, question_data)
        except Exception as e:
            log_debug(f"AskUserQuestion remote: send card failed: {e}")
            return self._make_decision("allow", "")

        # 阻塞等待飞书回答
        result = self._wait_for_answer(request_id)
        answers = result.get("answers", {})
        status = result.get("status", "timeout")

        # 更新飞书卡片
        try:
            result_card = self.card_builder.build_question_result_card(
                answers=answers, status=status
            )
            self.feishu.update_card(message_id, result_card)
        except Exception:
            pass

        # 将答案写入文件（Claude 通过 CLAUDE.md 指令读取）
        self._write_answer_file(questions, answers, status)

        log_debug(f"AskUserQuestion remote: answered={answers}, status={status}")

        return self._make_decision("allow", "")

    def _parse_questions(self, tool_input: Dict[str, Any]) -> list:
        """解析 AskUserQuestion 工具输入"""
        questions = []
        raw_questions = tool_input.get("questions", [])

        for i, q in enumerate(raw_questions):
            question_type = q.get("type", q.get("question_type", ""))
            if not question_type:
                options = q.get("options", [])
                question_type = "select" if options else "text"

            if question_type in ["single", "select"]:
                question_type = "select"
            elif question_type in ["multiple", "multi", "multi_select", "checkbox"]:
                question_type = "multi_select"

            raw_options = q.get("options", [])
            if raw_options and isinstance(raw_options[0], dict):
                options = [opt.get("label", opt.get("text", opt.get("id", ""))) for opt in raw_options]
            else:
                options = raw_options

            questions.append({
                "question_id": q.get("id", f"q{i+1}"),
                "question_text": q.get("question", q.get("text", "")),
                "question_type": question_type,
                "options": options,
                "answer": None
            })

        return questions

    def _wait_for_answer(self, request_id: str) -> Dict[str, Any]:
        """轮询等待飞书回答"""
        start_time = time.time()

        while (time.time() - start_time) < self.question_timeout:
            request_data = self.storage.get_request(request_id)

            if request_data and request_data.get("status") == "answered":
                answers = {}
                for q in request_data.get("questions", []):
                    answers[q["question_id"]] = q.get("answer", "")
                return {"answers": answers, "status": "success"}

            if request_data and request_data.get("status") == "cancelled":
                return {"answers": {}, "status": "cancel"}

            time.sleep(self.poll_interval)

        return {"answers": {}, "status": "timeout"}

    def _write_answer_file(self, questions: list, answers: dict, status: str):
        """将答案写入 data/last_answer.json"""
        try:
            answer_file = PROJECT_ROOT / "data" / "last_answer.json"
            answer_file.parent.mkdir(parents=True, exist_ok=True)
            with open(answer_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "answers": answers,
                    "status": status,
                    "timestamp": time.time(),
                    "questions": [
                        {"id": q["question_id"], "text": q["question_text"]}
                        for q in questions
                    ]
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[飞书Hook] 写入答案文件失败: {e}", file=sys.stderr)

    def _wait_for_decision(self, request_id: str) -> Dict[str, Any]:
        """等待用户决策（轮询模式）"""
        start_time = time.time()

        while (time.time() - start_time) < self.timeout:
            request_data = self.storage.get_request(request_id)

            if request_data and request_data.get("status") in ["allow", "deny"]:
                behavior = request_data["status"]
                return {
                    "behavior": behavior,
                    "message": request_data.get("user_message", "")
                }

            time.sleep(self.poll_interval)

        return {
            "behavior": "deny",
            "message": f"等待用户响应超时（{self.timeout}秒）"
        }

    def _make_decision(self, behavior: str, message: str) -> Dict[str, Any]:
        """构造 PermissionRequest 决策输出"""
        return {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": behavior,
                    "message": message
                }
            }
        }


def log_debug(msg: str):
    """写入调试日志"""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.time()}] {msg}\n")
    except:
        pass


def main():
    """Hook 入口点"""
    try:
        input_data = json.load(sys.stdin)

        tool_name = input_data.get("tool_name", "Unknown")
        log_debug(f"PermissionRequest called with tool_name={tool_name}")

        config = load_config()
        hook = PermissionHook(config)
        result = hook.handle_permission_request(input_data)

        print(json.dumps(result))
        sys.exit(0)

    except ValueError as e:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": str(e)}
            }
        }))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": f"Hook 执行失败: {str(e)}"}
            }
        }))
        sys.exit(0)


if __name__ == "__main__":
    main()
