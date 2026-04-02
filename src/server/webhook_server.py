#!/usr/bin/env python3
"""
FastAPI Webhook 服务器
接收飞书回调并更新权限请求状态
"""

import sys
import os
import json
import logging
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any
from Crypto.Cipher import AES

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from src.storage import PermissionStorage
from src.feishu.cards import CardBuilder, parse_card_action

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Feishu Permission Webhook")

# 全局变量（在启动时初始化）
storage = None
card_builder = CardBuilder()
encrypt_key = None


def decrypt_feishu_data(encrypted_data: str, key: str) -> Dict[str, Any]:
    """
    解密飞书加密数据

    尝试多种密钥处理方式
    """
    try:
        # Base64 解码密文
        encrypted_bytes = base64.b64decode(encrypted_data)
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]

        logger.info(f"Encrypted data: {len(encrypted_bytes)} bytes, IV: {len(iv)}, Ciphertext: {len(ciphertext)}")

        # 尝试多种密钥方式
        key_methods = [
            ("MD5 of key string", hashlib.md5(key.encode('utf-8')).digest()),
            ("SHA256 of key string (first 16)", hashlib.sha256(key.encode('utf-8')).digest()[:16]),
            ("SHA256 of key string (first 32)", hashlib.sha256(key.encode('utf-8')).digest()[:32]),
            ("Key string raw (first 16)", key.encode('utf-8')[:16].ljust(16, b'\0')),
            ("Base64 decoded key", base64.b64decode(key)),
            ("Base64 decoded key (MD5)", hashlib.md5(base64.b64decode(key)).digest()),
        ]

        for method_name, key_bytes in key_methods:
            try:
                # 调整密钥长度到 16/24/32
                if len(key_bytes) >= 32:
                    key_bytes = key_bytes[:32]
                elif len(key_bytes) >= 24:
                    key_bytes = key_bytes[:24]
                elif len(key_bytes) >= 16:
                    key_bytes = key_bytes[:16]
                else:
                    key_bytes = key_bytes.ljust(16, b'\0')

                logger.info(f"Trying method: {method_name}, key length: {len(key_bytes)}")

                cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
                decrypted = cipher.decrypt(ciphertext)

                # 尝试多种 padding 处理方式
                for pad_method in ["pkcs7", "manual"]:
                    try:
                        if pad_method == "pkcs7":
                            pad_len = decrypted[-1]
                            unpadded = decrypted[:-pad_len] if pad_len <= 16 and pad_len > 0 else decrypted
                        else:
                            # 手动去除尾部空字节
                            unpadded = decrypted.rstrip(b'\x00')

                        result = unpadded.decode('utf-8')
                        if result and result.strip():  # 非空
                            logger.info(f"Success with {method_name} + {pad_method}: {result[:100]}")
                            return json.loads(result)
                    except:
                        continue

            except Exception as e:
                logger.info(f"Method {method_name} failed: {e}")
                continue

        raise Exception("All decryption methods failed")

    except Exception as e:
        logger.error(f"Decryption error: {e}")
        raise


def load_config():
    """加载配置文件"""
    import yaml

    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return {
            "storage": {"path": "./data/permissions.json"},
            "webhook": {"port": 8080}
        }

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    global storage, encrypt_key
    config = load_config()
    storage_path = config.get("storage", {}).get("path", "./data/permissions.json")
    storage = PermissionStorage(storage_path)
    encrypt_key = config.get("feishu", {}).get("encrypt_key", "")
    logger.info(f"Webhook server started, storage: {storage_path}")
    if encrypt_key:
        logger.info("Encrypt key loaded")
    else:
        logger.warning("No encrypt key configured")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "feishu-permission-webhook"}


@app.get("/webhook/feishu")
async def verify_feishu_webhook(request: Request):
    """
    验证飞书 Webhook URL
    飞书会发送 GET 请求来验证 URL 是否有效
    """
    challenge = request.query_params.get("challenge")
    if challenge:
        logger.info(f"Received URL verification request, challenge: {challenge}")
        # 返回 JSON 格式的 challenge
        return JSONResponse(content={"challenge": challenge})
    # 无 challenge 时也返回成功响应
    return JSONResponse(content={"code": 0, "msg": "success"})


@app.post("/webhook/feishu")
async def handle_feishu_webhook(request: Request):
    """
    处理飞书 Webhook 回调

    支持加密和非加密两种模式
    """
    try:
        # 读取请求体
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')

        logger.info(f"Received webhook: {body_str[:200]}...")

        # 解析请求
        request_data = await request.json()

        # 检查是否是加密请求
        if "encrypt" in request_data:
            if not encrypt_key:
                logger.error("Received encrypted request but no encrypt key configured")
                return JSONResponse(content={"code": 1, "msg": "No encrypt key"})

            try:
                # 解密数据
                event_data = decrypt_feishu_data(request_data["encrypt"], encrypt_key)
                logger.info(f"Decrypted data: {json.dumps(event_data, ensure_ascii=False)[:200]}...")
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                return JSONResponse(content={"code": 1, "msg": "Decryption failed"})
        else:
            event_data = request_data

        # 检查是否是 URL 验证请求（包含 challenge）
        if "challenge" in event_data:
            challenge = event_data.get("challenge")
            logger.info(f"Received challenge verification request: {challenge}")
            return JSONResponse(content={"challenge": challenge})

        # 处理不同类型的事件
        handler = WebhookHandler(storage)
        result = await handler.handle_event(event_data)

        return JSONResponse(content={"code": 0, "msg": "success"})

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"code": 1, "msg": str(e)}
        )


class WebhookHandler:
    """Webhook 事件处理器"""

    def __init__(self, storage: PermissionStorage):
        self.storage = storage

    async def handle_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理飞书事件"""
        event_type = event_data.get("header", {}).get("event_type")

        if event_type == "im.message.receive_v1":
            return await self.handle_message_event(event_data)
        elif event_type == "card.action.trigger":
            return await self.handle_card_action(event_data)
        else:
            logger.info(f"Unhandled event type: {event_type}")
            return {}

    async def handle_message_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理消息事件
        用户回复文本消息（如 "允许"、"同意"、"拒绝" 等）
        """
        event = event_data.get("event", {})
        message = event.get("message", {})
        content_json = json.loads(message.get("content", "{}"))
        text = content_json.get("text", "").strip()

        # 查找最近的待处理请求
        pending_request = self.storage.get_latest_pending()

        if not pending_request:
            logger.warning("No pending request found")
            return {"error": "No pending request"}

        request_id = pending_request["request_id"]
        hook_event_name = pending_request.get("hook_event_name", "")

        # 处理 AskUserQuestion 的文本回复
        if hook_event_name == "AskUserQuestion":
            # 找到第一个未回答的问题
            questions = pending_request.get("questions", [])
            for q in questions:
                if not q.get("answer"):
                    question_type = q.get("question_type", "text")
                    question_id = q["question_id"]

                    if question_type == "text":
                        # 文本问题，直接保存答案
                        self.storage.update_question_answers(request_id, {question_id: text})
                        logger.info(f"Question {question_id} answered via text: {text} for request {request_id}")

                        # 检查是否所有问题都已回答
                        request_data = self.storage.get_request(request_id)
                        if request_data:
                            all_answered = all(q.get("answer") is not None for q in request_data.get("questions", []))
                            if all_answered:
                                self.storage.update_status(request_id, "answered", "所有问题已回答")
                        return {"success": True}

                    elif question_type == "select":
                        # 单选问题，检查回复是否匹配某个选项
                        options = q.get("options", [])
                        # 将回复与选项进行模糊匹配
                        matched_option = None
                        for opt in options:
                            if text.lower() in opt.lower() or opt.lower() in text.lower():
                                matched_option = opt
                                break

                        if matched_option:
                            self.storage.update_question_answers(request_id, {question_id: matched_option})
                            logger.info(f"Question {question_id} answered via text: {matched_option} for request {request_id}")

                            # 检查是否所有问题都已回答
                            request_data = self.storage.get_request(request_id)
                            if request_data:
                                all_answered = all(q.get("answer") is not None for q in request_data.get("questions", []))
                                if all_answered:
                                    self.storage.update_status(request_id, "answered", "所有问题已回答")
                            return {"success": True}
                        else:
                            # 选项不匹配，记录警告但继续尝试其他问题
                            logger.warning(f"Reply '{text}' does not match any options for {question_id}")
                            continue

            logger.warning(f"No matching question found for reply '{text}' in request {request_id}")
            return {"error": "No matching question"}

        # 处理 PermissionRequest 的权限决策
        text_lower = text.lower()
        decision = self._parse_text_decision(text_lower)

        # 更新请求状态
        self.storage.update_status(
            request_id,
            status=decision["behavior"],
            user_message=decision["message"]
        )

        logger.info(f"Request {request_id} updated to {decision['behavior']}")
        return {"success": True}

    async def handle_card_action(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理卡片按钮点击事件
        用户点击交互式卡片上的按钮
        """
        event = event_data.get("event", {})
        action = event.get("action", {})

        # 调试日志
        logger.info(f"Card action event: {json.dumps(event_data, ensure_ascii=False)[:500]}")

        # 提取 request_id 和决策
        # 注意：action.value 可能是对象或字符串，需要处理
        value = action.get("value", {})

        # 如果 value 是字符串，尝试解析为 JSON
        if isinstance(value, str):
            action_value = parse_card_action(value)
        else:
            action_value = value

        request_id = action_value.get("request_id")
        action_type = action_value.get("action")  # "submit", "cancel", "allow", "deny"

        logger.info(f"Card action: request_id={request_id}, action={action_type}")

        if not request_id:
            logger.warning(f"Invalid action value: {action_value}")
            return {"error": "Invalid action"}

        # 处理不同类型的动作
        if action_type == "answer":
            # AskUserQuestion 单选答案
            question_id = action_value.get("question_id")
            answer = action_value.get("answer", "")

            if question_id and answer:
                self.storage.update_question_answers(request_id, {question_id: answer})
                logger.info(f"Question {question_id} answered: {answer} for request {request_id}")
                return {"success": True}
            else:
                logger.warning(f"Invalid answer data: {action_value}")
                return {"error": "Invalid answer data"}

        elif action_type == "submit":
            # AskUserQuestion 提交答案（保留兼容性）
            form_data = self._extract_form_data(event_data)
            self.storage.update_question_answers(request_id, form_data)
            logger.info(f"Question answers updated for request {request_id}")
            return {"success": True}

        elif action_type == "skip":
            # 跳过文本问题
            request_data = self.storage.get_request(request_id)
            if request_data:
                # 找到第一个文本问题，设置为空字符串
                for q in request_data.get("questions", []):
                    if q.get("question_type") == "text" and not q.get("answer"):
                        q["answer"] = ""
                self.storage.save_request(request_id, request_data)
                # 检查是否所有问题都已回答
                all_answered = all(q.get("answer") is not None for q in request_data.get("questions", []))
                if all_answered:
                    self.storage.update_status(request_id, "answered", "用户跳过文本问题")
                logger.info(f"Question skipped for request {request_id}")
            return {"success": True}

        elif action_type == "cancel":
            # 取消请求
            self.storage.update_status(request_id, "cancelled", "用户取消")
            logger.info(f"Request {request_id} cancelled")
            return {"success": True}

        elif action_type in ["allow", "deny"]:
            # PermissionRequest 权限决策
            self.storage.update_status(
                request_id,
                status=action_type,
                user_message=f"用户通过卡片按钮响应: {action_type}"
            )
            logger.info(f"Request {request_id} updated to {action_type}")
            return {"success": True}

        else:
            # 兼容旧的 behavior 格式
            behavior = action_value.get("behavior")
            if behavior:
                self.storage.update_status(
                    request_id,
                    status=behavior,
                    user_message=f"用户通过卡片按钮响应: {behavior}"
                )
                logger.info(f"Request {request_id} updated to {behavior}")
                return {"success": True}

        logger.warning(f"Unknown action type: {action_type}")
        return {"error": "Unknown action type"}

    def _extract_form_data(self, event_data: Dict[str, Any]) -> Dict[str, str]:
        """
        从卡片交互事件中提取用户填写的答案

        Args:
            event_data: 飞书事件数据

        Returns:
            答案字典 {question_id: answer}
        """
        event = event_data.get("event", {})
        action = event.get("action", {})

        # 调试日志
        logger.info(f"Action data: {json.dumps(action, ensure_ascii=False)[:500]}")

        # 尝试多种可能的表单数据字段
        form_values = (
            action.get("formValues", {}) or
            action.get("form_values", {}) or
            action.get("formData", {}) or
            action.get("form_data", {})
        )

        logger.info(f"Form values: {json.dumps(form_values, ensure_ascii=False)[:500]}")

        answers = {}
        for key, value in form_values.items():
            # 提取 question_id 和实际答案
            # value 格式: {"question_id": "q1", "value": "用户输入的值"}
            if isinstance(value, dict):
                question_id = value.get("question_id", key)
                answer_value = value.get("value", "")

                # 对于多选，答案可能是数组
                if isinstance(answer_value, list):
                    answer_value = ",".join(answer_value)

                answers[question_id] = answer_value
            else:
                # 简单字符串值
                answers[key] = str(value)

        logger.info(f"Extracted answers: {answers}")
        return answers

    def _parse_text_decision(self, text: str) -> Dict[str, str]:
        """解析文本消息为决策"""
        allow_keywords = ["允许", "同意", "ok", "yes", "y", "允许执行", "批准", "pass"]
        deny_keywords = ["拒绝", "不", "no", "n", "deny", "取消", "fail"]

        if text in allow_keywords:
            return {"behavior": "allow", "message": "用户批准"}
        elif text in deny_keywords:
            return {"behavior": "deny", "message": "用户拒绝"}
        else:
            # 默认拒绝
            return {
                "behavior": "deny",
                "message": f"无法识别的响应: {text}"
            }


def main():
    """启动服务器"""
    import uvicorn
    import yaml

    config = load_config()
    port = config.get("webhook", {}).get("port", 8080)
    host = config.get("webhook", {}).get("host", "0.0.0.0")

    logger.info(f"Starting webhook server on {host}:{port}")

    uvicorn.run(
        "webhook_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
