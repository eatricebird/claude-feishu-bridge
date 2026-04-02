"""
存储模块 - 管理权限请求状态
使用 JSON 文件持久化存储
"""

import json
import time
import threading
import fcntl
from pathlib import Path
from typing import Dict, Any, Optional


class PermissionStorage:
    """权限请求存储管理"""

    def __init__(self, storage_path: str = "./data/permissions.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

        # 初始化存储文件
        if not self.storage_path.exists():
            self._write_data({})

    def save_request(self, request_id: str, data: Dict[str, Any]) -> bool:
        """
        保存请求数据

        Args:
            request_id: 请求唯一 ID
            data: 请求数据字典

        Returns:
            是否保存成功
        """
        with self.lock:
            try:
                all_data = self._read_data()
                all_data[request_id] = data
                self._write_data(all_data)
                return True
            except Exception as e:
                print(f"Error saving request: {e}", file=__import__('sys').stderr)
                return False

    def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        获取请求数据

        Args:
            request_id: 请求唯一 ID

        Returns:
            请求数据，不存在则返回 None
        """
        with self.lock:
            all_data = self._read_data()
            return all_data.get(request_id)

    def update_status(
        self,
        request_id: str,
        status: str,
        user_message: str = ""
    ) -> bool:
        """
        更新请求状态

        Args:
            request_id: 请求唯一 ID
            status: 新状态 (pending/allow/deny)
            user_message: 用户消息

        Returns:
            是否更新成功
        """
        with self.lock:
            try:
                all_data = self._read_data()
                if request_id in all_data:
                    all_data[request_id]["status"] = status
                    all_data[request_id]["user_message"] = user_message
                    all_data[request_id]["updated_at"] = time.time()
                    self._write_data(all_data)
                    return True
                return False
            except Exception as e:
                print(f"Error updating status: {e}", file=__import__('sys').stderr)
                return False

    def get_latest_pending(self) -> Optional[Dict[str, Any]]:
        """
        获取最新的待处理请求

        Returns:
            最新的待处理请求数据，不存在则返回 None
        """
        with self.lock:
            all_data = self._read_data()
            pending_requests = [
                (req_id, req_data)
                for req_id, req_data in all_data.items()
                if req_data.get("status") == "pending"
            ]

            if not pending_requests:
                return None

            # 按创建时间排序，返回最新的
            pending_requests.sort(
                key=lambda x: x[1].get("created_at", 0),
                reverse=True
            )

            return pending_requests[0][1]

    def update_question_answers(self, request_id: str, answers: Dict[str, str]) -> bool:
        """
        更新问题答案

        Args:
            request_id: 请求唯一 ID
            answers: 问题答案字典 {question_id: answer}

        Returns:
            是否更新成功
        """
        with self.lock:
            try:
                all_data = self._read_data()
                if request_id in all_data:
                    # 更新每个问题的答案
                    for q in all_data[request_id].get("questions", []):
                        q_id = q["question_id"]
                        if q_id in answers:
                            q["answer"] = answers[q_id]

                    # 只有当所有问题都已回答时才设置状态为 answered
                    all_answered = all(q.get("answer") is not None for q in all_data[request_id].get("questions", []))
                    if all_answered:
                        all_data[request_id]["status"] = "answered"
                    all_data[request_id]["updated_at"] = time.time()
                    self._write_data(all_data)
                    return True
                return False
            except Exception as e:
                print(f"Error updating question answers: {e}", file=__import__('sys').stderr)
                return False

    def cleanup_old_requests(self, max_age_hours: int = 24) -> int:
        """
        清理旧请求

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            清理的请求数量
        """
        with self.lock:
            try:
                all_data = self._read_data()
                cutoff_time = time.time() - (max_age_hours * 3600)

                original_count = len(all_data)
                cleaned_data = {
                    req_id: req_data
                    for req_id, req_data in all_data.items()
                    if req_data.get("created_at", 0) > cutoff_time
                }

                self._write_data(cleaned_data)
                return original_count - len(cleaned_data)
            except Exception as e:
                print(f"Error cleaning up: {e}", file=__import__('sys').stderr)
                return 0

    def _read_data(self) -> Dict[str, Any]:
        """读取所有数据"""
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_data(self, data: Dict[str, Any]):
        """写入所有数据（使用文件锁防止并发冲突）"""
        # 先写入临时文件
        temp_path = self.storage_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            # 获取文件锁
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # 原子性替换
        temp_path.replace(self.storage_path)


# 导入 os 模块用于 fsync
import os
