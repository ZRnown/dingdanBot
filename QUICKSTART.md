# 快速启动指南

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置环境变量

```bash
# 复制配置模板
cp env.example .env

# 编辑 .env 文件，至少需要配置：
# - TELEGRAM_BOT_TOKEN: 从 @BotFather 获取
# - API_AUTHORIZATION_TOKEN: API认证令牌
# - API_COOKIE: API Cookie
```

## 3. 运行程序

```bash
python main.py
```

## 4. 测试机器人

向机器人发送包含抖音链接的消息，例如：

```
请处理这个订单：https://v.douyin.com/XXXXX/
```

机器人应该回复："收到，已同步。"

## 5. 打包为 Linux 二进制

```bash
# 使用打包脚本
./build.sh

# 或手动打包
pyinstaller --onefile --name kefuBot main.py
```

打包后的文件位于 `dist/kefuBot`，可以直接在 Linux 系统上运行。

## 注意事项

- 确保 API 的认证信息有效
- 数据库文件 `orders.db` 会自动创建
- 程序启动时会自动同步今天的订单
- 默认每5分钟检查一次新订单（可在 .env 中配置）

