# Telegram 客服机器人

这是一个 Telegram 客服机器人，可以自动同步订单状态并响应包含抖音链接的消息。

## 功能特性

- 📦 自动获取和存储订单信息
- 🔄 定期检查新订单
- 🔍 自动检测消息中的抖音链接
- ✅ 自动同步订单到系统
- 💾 使用 SQLite 数据库存储订单

## 安装和配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `env.example` 为 `.env` 并填写配置：

```bash
cp env.example .env
```

编辑 `.env` 文件：

```env
# Telegram Bot Token (从 @BotFather 获取)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# API 配置
API_BASE_URL=http://183.136.134.132:168
API_AUTHORIZATION_TOKEN=Bearer your_token_here
API_COOKIE=your_cookie_here

# 数据库配置
DATABASE_PATH=orders.db

# 订单检查间隔（秒）
ORDER_CHECK_INTERVAL=300
PAGE_SIZE=500
```

### 3. 运行

```bash
python main.py
```

## 打包为 Linux 二进制文件

### 使用打包脚本

```bash
chmod +x build.sh
./build.sh
```

打包完成后，可执行文件位于 `dist/kefuBot`

### 手动打包

```bash
pyinstaller --onefile --name kefuBot main.py
```

## 使用说明

### 启动服务

1. 确保已配置 `.env` 文件
2. 运行程序：`python main.py` 或 `./kefuBot`（如果已打包）
3. 程序会自动：
   - 同步今天的所有订单
   - 定期检查新订单（默认每5分钟）
   - 监听 Telegram 消息

### 使用机器人

向机器人发送包含抖音链接的消息，例如：

```
请处理这个订单：https://v.douyin.com/XXXXX/
```

机器人会自动：
1. 检测消息中的抖音链接
2. 在数据库中查找对应订单
3. 调用同步 API
4. 回复"收到，已同步。"

## 项目结构

```
kefuBot/
├── main.py              # 主程序入口
├── bot.py               # Telegram Bot 逻辑
├── order_api.py         # 订单 API 调用
├── database.py          # 数据库操作
├── config.py            # 配置管理
├── requirements.txt     # Python 依赖
├── env.example          # 环境变量模板
├── build.sh             # 打包脚本
└── README.md            # 说明文档
```

## 注意事项

1. 确保 API 的认证信息（Token 和 Cookie）有效
2. 数据库文件 `orders.db` 会自动创建
3. 程序会忽略 SSL 证书验证（因为 API 使用自签名证书）
4. 建议在生产环境中使用 systemd 或 supervisor 管理进程

## 系统服务配置示例

创建 `/etc/systemd/system/kefubot.service`：

```ini
[Unit]
Description=Telegram Kefu Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/kefuBot
ExecStart=/path/to/kefuBot/kefuBot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl enable kefubot
sudo systemctl start kefubot
sudo systemctl status kefubot
```

## 许可证

MIT License

# dingdanBot
