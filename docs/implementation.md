# Claude Code 飞书桥接实现原理

## 概述

本项目实现了 Claude Code 与飞书（Lark）的双向桥接，支持两种交互场景：
1. **权限审批**：Claude 执行敏感操作时，发送飞书卡片请求用户批准
2. **远程提问**：Claude 向用户提问时，可通过飞书远程回答

## 核心架构

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Claude Code    │───▶│ PermissionRequest │───▶│   Feishu API    │
│                 │    │     Hook         │    │  (飞书开放平台)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │                       ▼                       ▼
         │              ┌──────────────┐      ┌──────────────┐
         │              │ JSON Storage │◀────▶│ Webhook 服务器│
         │              │ (permissions │      │ (FastAPI)    │
         │              │  .json)      │      └──────────────┘
         │              └──────────────┘              │
         │                       ▲                     │
         │              ┌──────────────┐              │
         └──────────────│ PreToolUse   │──────────────┘
                        │   Hook       │
                        └──────────────┘
```

## 数据流

### 权限审批流程（Bash、Write 等工具）

1. Claude 调用需要权限的工具 → 触发 PermissionRequest Hook
2. Hook 读取 stdin 中的工具信息 → 生成 `request_id`
3. Hook 发送飞书交互卡片（允许/拒绝按钮）
4. Hook 轮询 `storage` 等待状态变更
5. 用户在飞书点击按钮 → 飞书回调 webhook 服务器
6. Webhook 更新 `storage` 状态为 `allow`/`deny`
7. Hook 检测到状态变化 → 返回决策给 Claude

### 远程提问流程（AskUserQuestion）

1. Claude 调用 AskUserQuestion → 同时触发两个 Hook
2. **PermissionRequest Hook**：
   - 发送飞书交互卡片（问题选项）
   - 阻塞轮询等待飞书回答
   - 收到回答后写入 `data/last_answer.json`
   - 返回 `allow`（抑制终端 UI）
3. **PreToolUse Hook**：
   - 立即返回 `{}`
   - 其存在使终端选择框能正常显示
4. 用户可从**任一端**回答：
   - 在终端回答 → Claude 直接获取结果
   - 在飞书回答 → Claude 从 `data/last_answer.json` 读取
5. **关键特性**：终端和飞书**同时显示**，双通道并行

## Hook 协议

### PermissionRequest Hook

**输入**（stdin）：
```json
{
  "session_id": "abc123",
  "tool_name": "Bash",
  "tool_input": {
    "command": "rm -rf node_modules",
    "description": "Remove node_modules"
  }
}
```

**输出**（stdout）：
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "allow|deny",
      "message": "原因说明"
    }
  }
}
```

### PreToolUse Hook（AskUserQuestion）

**输入**（stdin）：
```json
{
  "session_id": "abc123",
  "tool_input": {
    "questions": [...]
  }
}
```

**输出**（stdout）：
```json
{}
```

返回空对象 `{}` 让工具正常执行，其存在使终端 UI 能够显示。

## 存储结构

### permissions.json

```json
{
  "request_id": {
    "request_id": "uuid",
    "session_id": "session_id",
    "hook_event_name": "PermissionRequest|AskUserQuestion",
    "tool_name": "Bash",
    "tool_input": {...},
    "status": "pending|allow|deny|answered|cancelled",
    "created_at": 1234567890.0,
    "updated_at": 1234567890.0,
    "feishu_message_id": "msg_id",
    "questions": [...],
    "user_message": "用户说明"
  }
}
```

### last_answer.json

```json
{
  "answers": {
    "q1": "用户选择的答案"
  },
  "status": "success|timeout|cancel",
  "timestamp": 1234567890.0,
  "questions": [
    {"id": "q1", "text": "问题文本"}
  ]
}
```

## 并发控制

使用 `fcntl.flock` + 临时文件原子替换实现跨进程文件锁：

```python
# 写入时先写临时文件，然后原子性替换
temp_path = self.storage_path.with_suffix('.tmp')
with open(temp_path, 'w') as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    json.dump(data, f)
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
temp_path.replace(self.storage_path)  # 原子操作
```

## 飞书卡片设计

### 权限审批卡片
- 显示工具名称和命令/描述
- 两个交互按钮："允许"、"拒绝"
- 用户点击后触发 webhook 回调

### 问答交互卡片
- 显示问题文本
- 根据选项类型显示按钮或输入框
- 提交后触发 webhook 回调

## 关键文件

| 文件 | 作用 |
|------|------|
| `src/hooks/permission_request.py` | PermissionRequest Hook，处理权限审批和远程提问 |
| `src/hooks/ask_user_question.py` | PreToolUse Hook，启用终端 UI |
| `src/server/webhook_server.py` | FastAPI Webhook 服务器，处理飞书回调 |
| `src/storage.py` | 存储管理，JSON 文件 + 文件锁 |
| `src/feishu/client.py` | 飞书 OpenAPI 客户端（使用 curl） |
| `src/feishu/cards.py` | 飞书卡片构建器 |
| `config/config.yaml` | 配置文件（飞书凭据、超时等） |
| `.claude/settings.local.json` | Claude Code Hook 注册 |

## 配置示例

```yaml
# config/config.yaml
feishu:
  app_id: "cli_xxxxx"
  app_secret: "xxxxx"
  user_id: "ou_xxxxx"
  encrypt_key: "可选的加密密钥"

storage:
  path: "./data/permissions.json"

permissions:
  timeout: 300        # 权限请求超时（秒）
  poll_interval: 2     # 轮询间隔（秒）

ask_user_question:
  timeout: 300        # 问答超时（秒）
  poll_interval: 3

webhook:
  host: "0.0.0.0"
  port: 8080
```

## 飞书事件订阅

需要订阅的事件：
- `im.message.receive_v1`：接收文本消息（"允许"/"拒绝"）
- `card.action.trigger`：接收卡片按钮点击

回调 URL：`http://your-server:8080/webhook/feishu`

## 部署

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置文件
cp config/config.yaml.example config/config.yaml
# 编辑 config/config.yaml 填入飞书凭据

# 3. 启动 webhook 服务器
python3 src/server/webhook_server.py

# 4. 配置 Claude Code Hooks（.claude/settings.local.json）
# 已自动配置，确保路径正确

# 5. 测试
./scripts/test_hook.sh
```

## 设计决策

### 为什么使用 curl 而非 requests？

在某些网络环境下（如企业内网、特殊 DNS 配置），`requests` 库可能遇到 DNS 解析问题。使用 `curl` 子进程调用更稳定可靠。

### 为什么 PermissionRequest Hook 阻塞等待？

Hook 阻塞期间，Claude Code 会等待 Hook 返回后再继续执行。这确保了：
1. 在收到用户回复前，工具不会执行
2. Hook 可以控制工具是否被允许执行

### 为什么需要 PreToolUse Hook？

虽然 PreToolUse Hook 只返回 `{}`，但其存在改变了 Claude Code 的行为：
- **没有 PreToolUse**：PermissionRequest 返回 `allow` 会完全跳过工具执行，无任何输出
- **有 PreToolUse 返回 `{}`**：工具正常执行，终端 UI 显示

这实现了双通道并行的效果。

## 注意事项

1. **Hook 超时**：PermissionRequest Hook 超时默认 360 秒，问答超时应小于此值
2. **文件权限**：确保 `data/` 目录可写
3. **防火墙**：Webhook 服务器端口需要对外开放或使用内网穿透
4. **飞书应用**：需要申请飞书应用并配置事件订阅
