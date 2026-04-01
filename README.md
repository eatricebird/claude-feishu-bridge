# 飞书权限通知系统

通过飞书 App 远程处理 Claude Code 的权限请求和用户问题。当 Claude Code 需要执行敏感操作或向用户提问时，会在飞书中收到卡片通知，点击按钮即可响应。

> **⚠️ 安全提示**：本项目的 `config/config.yaml` 包含敏感凭据，已被 `.gitignore` 排除。部署时请务必从 `config.yaml.example` 复制并填入自己的凭据，切勿将真实凭据提交到版本控制系统。

## 一、系统原理

### 1.1 执行流程

```
┌─────────────┐      权限请求      ┌──────────────┐
│ Claude Code │ ───────────────>  │ Hook 脚本    │
└─────────────┘                   └──────────────┘
                                         │
                                         │ 发送飞书卡片
                                         ▼
                                   ┌─────────────┐
                                   │ 飞书 App     │
                                   │ (收到通知)   │
                                   └─────────────┘
                                         │
                                         │ 点击按钮响应
                                         ▼
┌─────────────┐      更新状态      ┌──────────────┐
│ Webhook     │ <─────────────────│ 存储层        │
│ 服务器      │                    └──────────────┘
└─────────────┘                          │
                                         │ 检测状态变化
                                         ▼
                                   ┌──────────────┐
                                   │ Hook 脚本     │
                                   │ (轮询检测)    │
                                   └──────────────┘
                                         │
                                         │ 返回决策
                                         ▼
┌─────────────┐      执行/拒绝      ┌──────────────┐
│ Claude Code │ <───────────────── │ 权限决策     │
└─────────────┘                   └──────────────┘
```

### 1.2. 核心组件

| 组件 | 功能 | 技术栈 |
|------|------|--------|
| PermissionRequest Hook | 拦截权限请求和用户问题，发送飞书卡片 | Python 3 |
| PreToolUse Hook | 激活终端 UI 显示（返回 `{}`） | Python 3 |
| Webhook 服务器 | 接收飞书回调，更新请求状态 | FastAPI + Uvicorn |
| 飞书客户端 | 发送消息卡片 | Python + curl |
| 存储层 | 持久化请求状态 | JSON 文件 |
| 内网穿透 | 暴露本地服务到公网 | Natapp |

本项目仅仅包含`Hook脚本`,`Webhook 服务器`,`存储层`. 飞书客户端，内网穿透需要客户自行搭建和配置（可以参考本文操作）

#### 1.2.1. 存储层的作用：
  - 存储每个权限请求的状态（待批准/已批准/已拒绝）
  - Hook 脚本写入请求 → Webhook 服务器更新状态 → Hook 脚本轮询检测变化

#### 1.2.2. 为什么要内网穿透？
如果本系统（claude code + HOOK脚本 +  Webhook 服务器）部署在内网（比如家中，公司内网等），那么必须做内网穿透才能和运行在外网环境的手机通信。  
如果系统本身就有公网IP就不必内网穿透。

---

## 二、快速部署

### 2.1. 前置要求

- Python 3.8+
- 飞书账号
- 系统有公网 IP 或使用内网穿透工具

### 2.2. 安装步骤

#### 2.2.1. 克隆项目

```bash
git clone https://github.com/eatricebird/claude-feishu-bridge.git ~/
```

#### 2.2.2. 安装依赖

```bash
pip install -r requirements.txt
```

依赖列表：
- fastapi==0.104.1
- uvicorn[standard]==0.24.0
- requests==2.31.0
- pyyaml==6.0.1
- pycryptodome==3.19.0

#### 2.2.3. 配置应用

```bash
# 复制配置模板
cp config/config.yaml.example config/config.yaml

# 编辑配置文件，填入你的飞书凭据
vi config/config.yaml
```

#### 2.2.4. 配置飞书应用

详见下方"配置飞书"章节。

#### 2.2.5. 配置内网穿透
详见下方"内网穿透配置"章节

#### 2.2.6. 启动服务

```bash
# 终端 1：启动 Webhook 服务器
cd ~/claude-feishu-bridge
python3 src/server/webhook_server.py

# 终端 2：启动内网穿透,YOUR_TOKEN可以在配置内网穿透时获取
./natapp -authtoken=YOUR_TOKEN -log=stdout
```

#### 2.2.7. 部署 Hook
参考"部署 Claude Code Hook"章节

至此部署完成。

---

## 三、配置飞书

### 3.1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 点击 **"创建应用"** → **"自建应用"**
3. 填写应用信息并创建

### 3.2. 获取应用凭证

在应用详情页的 **"凭证与基础信息"** 中记录：

| 信息 | 说明 | 示例 |
|------|------|------|
| App ID | 应用唯一标识 | `cli_xxxxxxxxxxxxx` |
| App Secret | 应用密钥 | `xxxxxxxxxxxxxxxxxx` |

### 3.3. 配置权限

在 **"权限管理"** 中开通以下权限：

- `im:message` - 发送和接收消息
- `im:message:send_as_bot` - 机器人发送消息

### 3.4. 配置事件订阅

在 **"事件与回调"** → **"加密策略"** 中：

1. 选择 **"Encrypt Key"** 模式
2. 点击 **"生成 Encrypt Key"** 并记录
3. 在 **"回调配置"** 中：
   - 订阅方式：`将回调发送至 开发者服务器`
   - 请求地址：`http://${your public url}/webhook/feishu`
   - 订阅事件：
    - `card.action.trigger`
4. 在 **"事件配置"** 中：
   - 订阅方式：`将事件发送至 开发者服务器`
   - 请求地址：`http://${your public url}/webhook/feishu`
   - 订阅事件：
     - `im.message.receive_v1`

其中，${your public url}参考"内网穿透配置"
### 3.5. 发布应用

1. 在 **"版本管理与发布"** 中创建版本
2. 申请发布（自建应用通常即时通过）

### 3.6. 获取用户 open_id
参考
```
https://open.feishu.cn/document/faq/trouble-shooting/how-to-obtain-openid
```

### 3.7. 填写配置文件

```bash
# 复制配置模板
cp config/config.yaml.example config/config.yaml

# 编辑配置文件，填入从飞书开放平台获取的凭证
vi config/config.yaml
```

配置文件格式：

```yaml
feishu:
  app_id: "cli_xxxxxxxxxxxxx"        # 你的 App ID
  app_secret: "xxxxxxxxxxxxxxxxxx"   # 你的 App Secret
  user_id: "ou_xxxxxxxxxxxxx"        # 你的 open_id
  encrypt_key: "xxxxxxxxxxxxxxxxxx"  # Encrypt Key
```

---

## 四、内网穿透配置

由于本地开发环境通常没有公网 IP，需要使用内网穿透工具。

### 4.1 使用 Natapp（推荐）

#### 4.1.1. 注册获取 Token

1. 访问 https://natapp.cn/
2. 免费注册并登录
3. 在 **"我的隧道"** 中创建免费隧道
4. 复制 authtoken

#### 4.1.2. 下载 Natapp

```
https://natapp.cn/download
```

#### 4.1.3. 配置本地端口

在 Natapp 网页的隧道配置中，将 **"本地端口"** 设置为 `8080`

#### 4.1.4. 启动 Natapp

```bash
./natapp -authtoken=YOUR_TOKEN -log=stdout
```

启动后会显示：
```
Tunnel established at http://xxxxx.natappfree.cc
```

这个 URL 就是你的公网地址。

## 五、部署 Claude Code Hook

### 5.1 Hook 部署

在项目目录创建 `.claude/settings.local.json`：

```bash
mkdir -p ~/claude-feishu-bridge/.claude
cat > ~/claude-feishu-bridge/.claude/settings.local.json <<EOF
{
  "permissions": {
    "allow": [
      "AskUserQuestion",
      "Bash(python3 ~/claude-feishu-bridge/src/hooks/permission_request.py)",
      "Bash(python3 ~/claude-feishu-bridge/src/hooks/ask_user_question.py)"
    ]
  },
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/claude-feishu-bridge/src/hooks/permission_request.py",
            "timeout": 360
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/claude-feishu-bridge/src/hooks/ask_user_question.py",
            "timeout": 660
          }
        ]
      }
    ]
  }
}
EOF
```

### 5.2 Hook 说明

| Hook 类型 | 功能 | 触发时机 |
|----------|------|---------|
| PermissionRequest | 拦截权限请求，发送飞书卡片（权限审批或远程提问） | 工具需要权限时，或 Claude 向用户提问时 |
| PreToolUse (AskUserQuestion) | 激活终端选择框显示 | Claude 向用户提问时 |

**说明**：PermissionRequest Hook 统一处理权限审批和远程提问，PreToolUse Hook 的存在让终端 UI 能够正常显示。

### 5.3 验证部署

```bash
# 检查配置是否生效
cat ~/claude-feishu-bridge/.claude/settings.local.json

# 测试 Hook
./scripts/test_hook.sh
```

---

## 六、完整部署流程(上述流程的完整串联)

### 6.1. 第一次部署

#### 6.1.1. 准备项目

```bash
cd ~/claude-feishu-bridge
pip install -r requirements.txt
```

#### 6.1.2. 配置飞书

按照"配置飞书"章节完成飞书应用的创建和配置，获取：
- App ID
- App Secret
- Encrypt Key
- 你的 open_id

#### 6.1.3. 填写配置文件

```bash
# 复制配置模板
cp config/config.yaml.example config/config.yaml

# 编辑配置文件，填入飞书凭证
vi config/config.yaml
```

#### 6.1.4. 配置 Claude Code Hook

Hook 已包含在项目配置中，确保 `~/claude-feishu-bridge/.claude/settings.local.json` 文件存在：

```bash
cat ~/claude-feishu-bridge/.claude/settings.local.json
```

#### 6.1.5. 启动服务

```bash
# 终端 1：Webhook 服务器
python3 src/server/webhook_server.py

# 终端 2：内网穿透
./natapp -authtoken=YOUR_TOKEN -log=stdout
```

#### 6.1.6. 配置飞书回调

在飞书开放平台的 **"回调配置"** 和 **"事件配置"** 中，填入 Natapp 提供的 URL：

```
http://xxxxx.natappfree.cc/webhook/feishu
```

### 6.2. 日常使用

每次使用前启动服务：

```bash
# 终端 1
cd ~/claude-feishu-bridge
python3 src/server/webhook_server.py

# 终端 2
./natapp -authtoken=YOUR_TOKEN -log=stdout
```

然后在 Claude Code 中正常工作，权限请求会自动发送到飞书。

---

## 七、项目结构

```
claude-feishu-bridge/
├── .claude/
│   └── settings.local.json       # Claude Code Hook 配置
├── config/
│   └── config.yaml               # 应用配置
├── data/
│   ├── permissions.json          # 权限请求存储
│   └── hook_debug.log            # Hook 调试日志
├── src/
│   ├── hooks/
│   │   ├── permission_request.py # PermissionRequest Hook
│   │   └── ask_user_question.py  # PreToolUse Hook (AskUserQuestion)
│   ├── server/
│   │   └── webhook_server.py     # FastAPI Webhook 服务器
│   ├── feishu/
│   │   ├── client.py             # 飞书 API 客户端
│   │   └── cards.py              # 消息卡片构建器
│   └── storage.py                # 状态存储管理
├── scripts/
│   ├── start.sh                  # 一键启动脚本
│   └── test_hook.sh             # Hook 测试脚本
├── requirements.txt
└── README.md
```

---

## 八、配置选项

### config/config.yaml

```yaml
# 飞书配置
feishu:
  app_id: ""          # 飞书应用 ID
  app_secret: ""       # 飞书应用密钥
  user_id: ""          # 接收通知的用户 open_id
  encrypt_key: ""      # 飞书 Encrypt Key

# Webhook 服务器配置
webhook:
  port: 8080           # Webhook 服务器端口
  host: "0.0.0.0"       # 监听地址

# 存储配置
storage:
  path: "./data/permissions.json"  # 请求数据存储路径

# 权限请求配置
permissions:
  timeout: 300         # 等待用户响应的超时时间（秒）
  poll_interval: 2     # 轮询间隔（秒）
```

---

## 九、故障排除

### 问题 1：Hook 没有触发

**检查**：
```bash
cat ~/.claude/settings.local.json
```

确保 Hook 配置正确且路径有效。

### 问题 2：飞书没有收到通知
**检查**：
脚本`permission_request.py`中是否正确读取了配置文件，并且飞书 API 调用没有报错。可以在脚本中添加日志输出，查看是否成功发送了请求。

### 问题 3：点击按钮后无响应

**检查**：
1. Webhook 服务器是否运行：`ps aux | grep webhook_server`
1. Webhook 服务器是否正常工作:
   - 浏览器输入`http://g52ba9a6.natappfree.cc/health`（替换为你的 Natapp URL）应该返回 `{"status":"ok"}`
2. Natapp 是否运行：`ps aux | grep natapp`
3. 内网穿透 URL 是否正确配置到飞书
4. 内网穿透 URL 是否更换了域名，如果是，更新飞书回调 URL 和事件 URL。

### 问题 4：超时错误

**原因**：未在 5 分钟内响应

**解决**：增加 `config.yaml` 中的 `permissions.timeout` 值

### 问题 5：DNS 解析失败

**症状**：`Temporary failure in name resolution`

**解决**：
```bash
# 重新设置 DNS
sudo tee /etc/resolv.conf > /dev/null <<EOF
nameserver 223.5.5.5
nameserver 8.8.8.8
EOF
```

---

## 十、高级配置

### 使用 systemd 自动启动服务

创建 `/etc/systemd/system/feishu-webhook.service`：

```ini
[Unit]
Description=Feishu Permission Webhook Server
After=network.target

[Service]
Type=simple
User=alan
WorkingDirectory=~/claude-feishu-bridge
ExecStart=/usr/bin/python3 src/server/webhook_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable feishu-webhook
sudo systemctl start feishu-webhook
```

---

## 十一、安全建议

1. **保护配置文件**：`config/config.yaml` 包含敏感信息
2. **限制网络访问**：Webhook 服务器只监听本地
3. **验证签名**：生产环境建议启用飞书签名验证
4. **定期清理**：定期清理过期的权限请求记录

---

## 十二、许可证

MIT License

---

## 十三、贡献

欢迎提交 Issue 和 Pull Request！
