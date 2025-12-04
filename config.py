import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    # Telegram Bot配置
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # API配置
    API_BASE_URL = os.getenv('API_BASE_URL', 'http://183.136.134.132:168')
    API_AUTHORIZATION_TOKEN = os.getenv('API_AUTHORIZATION_TOKEN', '')
    API_COOKIE = os.getenv('API_COOKIE', '')
    
    # 数据库配置
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'orders.db')
    
    # 订单检查配置
    ORDER_CHECK_INTERVAL = int(os.getenv('ORDER_CHECK_INTERVAL', '300'))  # 默认5分钟
    PAGE_SIZE = int(os.getenv('PAGE_SIZE', '500'))
    SYNC_TASK_INTERVAL = int(os.getenv('SYNC_TASK_INTERVAL', '180'))  # 默认3分钟
    
    @classmethod
    def validate(cls):
        """验证必要的配置项"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN 未配置")
        if not cls.API_AUTHORIZATION_TOKEN:
            raise ValueError("API_AUTHORIZATION_TOKEN 未配置")

