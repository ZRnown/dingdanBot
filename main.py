#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import threading
import time
from datetime import datetime
import logging
from config import Config
from database import Database
from order_api import OrderAPI
from bot import TelegramBot

class OrderSyncService:
    def __init__(self, db: Database, order_api: OrderAPI):
        self.db = db
        self.order_api = order_api
        self.running = False
        self.last_order_id = 0
    
    def sync_recent_orders(self):
        """同步最近两天的订单"""
        logging.info("=== 开始同步最近2天的订单 ===")
        
        # 获取选中的第三方ID
        shequ_ids = self.db.get_selected_shequ_ids()
        if self.db.is_all_shequ_selected():
            shequ_ids = None  # None表示获取全部
        
        if shequ_ids:
            logging.info(f"已选择第三方: {shequ_ids}")
        else:
            logging.info("获取全部第三方的订单")
        
        orders = self.order_api.get_recent_orders(days=2, shequ_ids=shequ_ids)
        
        if orders:
            # 如果选择了特定第三方，只保存属于这些第三方的订单
            if shequ_ids:
                filtered_orders = [order for order in orders if order.get('ShequId', 0) in shequ_ids]
                logging.info(f"过滤后剩余 {len(filtered_orders)} 个订单（属于选中的第三方）")
                orders = filtered_orders
            
            count = self.db.insert_orders_batch(orders)
            logging.info(f"成功存储 {count} 个订单")
            
            # 更新最后处理的订单ID
            if orders:
                self.last_order_id = max(order.get('Id', 0) for order in orders)
                logging.info(f"最后处理的订单ID: {self.last_order_id}")
        else:
            logging.info("没有获取到订单")
        
        # 清理超过2天的订单
        deleted_count = self.db.delete_expired_orders(days=2)
        if deleted_count > 0:
            logging.info(f"已清理 {deleted_count} 个过期订单")
        
        logging.info("=== 同步完成 ===")
    
    def check_new_orders(self):
        """检查新订单"""
        logging.info("=== 检查新订单 ===")
        
        # 获取选中的第三方ID
        shequ_ids = self.db.get_selected_shequ_ids()
        if self.db.is_all_shequ_selected():
            shequ_ids = None
        
        new_orders = self.order_api.get_new_orders(
            last_order_id=self.last_order_id,
            days=2,
            shequ_ids=shequ_ids
        )
        
        if new_orders:
            logging.info(f"发现 {len(new_orders)} 个新订单")
            
            # 如果选择了特定第三方，只保存属于这些第三方的订单
            if shequ_ids:
                filtered_orders = [order for order in new_orders if order.get('ShequId', 0) in shequ_ids]
                logging.info(f"过滤后剩余 {len(filtered_orders)} 个订单（属于选中的第三方）")
                new_orders = filtered_orders
            
            count = self.db.insert_orders_batch(new_orders)
            logging.info(f"成功存储 {count} 个新订单")
            
            # 更新最后处理的订单ID
            self.last_order_id = max(order.get('Id', 0) for order in new_orders)
            logging.info(f"最后处理的订单ID: {self.last_order_id}")
        else:
            logging.info("没有新订单")
        
        # 清理超过2天的订单
        deleted_count = self.db.delete_expired_orders(days=2)
        if deleted_count > 0:
            logging.info(f"已清理 {deleted_count} 个过期订单")
        
        logging.info("=== 检查完成 ===")
    
    def cleanup_expired_orders(self):
        """清理超过2天的订单"""
        logging.info("=== 清理过期订单 ===")
        deleted_count = self.db.delete_expired_orders(days=2)
        if deleted_count > 0:
            logging.info(f"已清理 {deleted_count} 个超过2天的订单")
        else:
            logging.info("没有需要清理的过期订单")
        logging.info("=== 清理完成 ===")
    
    def run_periodic_check(self):
        """定期检查新订单"""
        self.running = True
        
        # 首次同步最近2天的订单
        self.sync_recent_orders()
        
        # 定期检查新订单和清理过期订单
        cleanup_counter = 0
        cleanup_interval = 3600  # 每小时清理一次（3600秒）
        
        while self.running:
            time.sleep(Config.ORDER_CHECK_INTERVAL)
            if self.running:
                self.check_new_orders()
                
                # 定期清理过期订单（每小时一次）
                cleanup_counter += Config.ORDER_CHECK_INTERVAL
                if cleanup_counter >= cleanup_interval:
                    self.cleanup_expired_orders()
                    cleanup_counter = 0
    
    def stop(self):
        """停止服务"""
        self.running = False

def main():
    """主函数"""
    Config.setup_logging()
    logging.info("=" * 50)
    logging.info("Telegram 客服机器人启动中...")
    logging.info("=" * 50)
    
    # 验证配置
    try:
        Config.validate()
    except ValueError as e:
        logging.error(f"配置错误: {e}")
        logging.error("请检查 .env 文件中的配置")
        return
    
    # 初始化组件
    logging.info("初始化数据库...")
    db = Database()
    
    logging.info("初始化订单API...")
    order_api = OrderAPI()
    
    logging.info("初始化订单同步服务...")
    sync_service = OrderSyncService(db, order_api)
    
    logging.info("初始化Telegram Bot...")
    bot = TelegramBot(db, order_api)
    
    # 在后台线程中运行订单同步服务
    sync_thread = threading.Thread(target=sync_service.run_periodic_check, daemon=True)
    sync_thread.start()
    
    logging.info("所有服务已启动")
    logging.info("=" * 50)
    logging.info("按 Ctrl+C 停止服务")
    logging.info("=" * 50)
    
    try:
        # 运行Telegram Bot（阻塞）
        bot.run()
    except KeyboardInterrupt:
        logging.info("正在停止服务...")
        sync_service.stop()
        logging.info("服务已停止")

if __name__ == '__main__':
    main()

