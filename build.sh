#!/bin/bash

# Telegram Bot 打包脚本
# 用于将项目打包为 Linux 可执行文件

echo "开始打包 Telegram Bot..."

# 检查是否安装了 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller 未安装，正在安装..."
    pip install pyinstaller
fi

# 清理之前的构建文件
echo "清理之前的构建文件..."
rm -rf build dist __pycache__ *.spec

# 打包
echo "开始打包..."
pyinstaller --onefile \
    --name kefuBot \
    --add-data "env.example:." \
    --hidden-import=telegram \
    --hidden-import=telegram.ext \
    --hidden-import=requests \
    --hidden-import=dotenv \
    --hidden-import=schedule \
    --hidden-import=sqlite3 \
    --hidden-import=urllib3 \
    --clean \
    main.py

if [ $? -eq 0 ]; then
    echo "打包成功！"
    echo "可执行文件位置: dist/kefuBot"
    echo ""
    echo "使用说明:"
    echo "1. 将 dist/kefuBot 复制到 Linux 服务器"
    echo "2. 创建 .env 文件并配置相关参数"
    echo "3. 运行: ./kefuBot"
else
    echo "打包失败！"
    exit 1
fi

