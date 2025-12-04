import re
import asyncio
import json
import time
from datetime import datetime
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from database import Database
from order_api import OrderAPI
from config import Config

class TelegramBot:
    def __init__(self, db: Database, order_api: OrderAPI):
        self.db = db
        self.order_api = order_api
        self.bot_token = Config.TELEGRAM_BOT_TOKEN
        self.sync_interval = Config.SYNC_TASK_INTERVAL
        self.target_refund_statuses = ['退单中', '已退款', '已退单']
        
        # 抖音链接正则表达式
        self.douyin_url_pattern = re.compile(
            r'https?://v\.douyin\.com/[A-Za-z0-9_-]+/?',
            re.IGNORECASE
        )
    
    def extract_douyin_urls(self, text: str) -> list:
        """从文本中提取所有抖音链接"""
        urls = self.douyin_url_pattern.findall(text)
        # 清理URL，确保格式一致
        cleaned_urls = []
        for url in urls:
            # 使用数据库的标准化方法
            normalized = self.db.normalize_url(url)
            if normalized:
                cleaned_urls.append(normalized)
        return cleaned_urls
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理收到的消息"""
        if not update.message or not update.message.text:
            return
        
        message_text = update.message.text
        chat_id = update.message.chat_id
        message_id = update.message.message_id
        
        print(f"收到消息: {message_text[:100]}... (来自用户 {chat_id})")
        
        douyin_urls = self.extract_douyin_urls(message_text)
        if not douyin_urls:
            return
        
        selected_shequ_ids = set(self.db.get_selected_shequ_ids())
        is_all_selected = self.db.is_all_shequ_selected()
        
        for url in douyin_urls:
            print(f"找到抖音链接: {url}")
            order = self.db.find_order_by_douyin_url(url)
            if not order:
                print(f"未找到链接 {url} 对应的订单")
                continue
            
            order_id = order.get('order_id')
            order_shequ_id = order.get('shequ_id', 0)
            print(f"找到订单 ID: {order_id}, 第三方ID: {order_shequ_id}")
            
            if not is_all_selected and selected_shequ_ids and order_shequ_id not in selected_shequ_ids:
                print(f"订单 {order_id} 不属于选中的第三方分类，跳过处理")
                await update.message.reply_text(
                    "订单不属于当前选中的第三方分类，已跳过处理。",
                    reply_to_message_id=message_id
                )
                continue
            
            if self.db.is_refund_status(order):
                print(f"订单 {order_id} 处于退单状态，跳过同步")
                # 不再回复中间状态，只在最终状态时通知
                continue
            
            self.db.add_sync_task(
                order_id=order_id,
                chat_id=chat_id,
                message_id=message_id,
                initial_attempts=0,
                max_attempts=0,
                douyin_url=order.get('douyin_url', ''),
                shequ_id=order.get('shequ_id', 0),
                order_sn=order.get('order_sn', '')
            )
            
            task = self.db.get_sync_task(order_id)
            if task:
                await self._process_single_sync_task(context.bot, task)

    async def handle_set_shequ_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /setshequ 命令 - 显示第三方设置界面"""
        # 获取第三方列表
        shequ_list = self.order_api.get_shequ_list()
        
        if not shequ_list:
            await update.message.reply_text("获取第三方列表失败，请稍后重试。")
            return
        
        # 获取当前选中的第三方
        selected_ids = set(self.db.get_selected_shequ_ids())
        
        # 构建键盘（两列布局）
        keyboard = []
        row = []
        for i, shequ in enumerate(shequ_list):
            shequ_id = shequ.get('Id')
            shequ_name = shequ.get('SName', f'第三方 {shequ_id}')
            is_selected = shequ_id in selected_ids
            
            # 添加选中标记：选中的显示 ✅，未选中的显示 ❌
            prefix = "✅ " if is_selected else "❌ "
            button_text = f"{prefix}{shequ_name}"
            
            row.append(InlineKeyboardButton(
                button_text,
                callback_data=f"shequ_toggle_{shequ_id}"
            ))
            
            # 每两个按钮一行，或者到达最后一个
            if len(row) == 2 or i == len(shequ_list) - 1:
                keyboard.append(row)
                row = []
        
        # 添加"全部"和"完成"按钮
        is_all_selected = len(selected_ids) == 0
        all_prefix = "✅ " if is_all_selected else "❌ "
        keyboard.append([InlineKeyboardButton(
            f"{all_prefix}全部（获取所有第三方）",
            callback_data="shequ_toggle_all"
        )])
        keyboard.append([InlineKeyboardButton(
            "✅ 完成设置",
            callback_data="shequ_done"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "请选择要获取订单的第三方：\n\n"
        if selected_ids:
            message_text += f"当前已选择 {len(selected_ids)} 个第三方\n"
        else:
            message_text += "当前设置为：获取全部第三方\n"
        message_text += "\n点击第三方名称可以切换选中状态\n点击'完成设置'保存配置"
        
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    
    async def handle_shequ_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理第三方选择的回调"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "shequ_done":
            # 完成设置，立即获取对应第三方近两天的订单
            await query.edit_message_text("✅ 设置已保存。\n正在获取对应第三方订单...")
            
            # 获取当前选中的第三方ID
            selected_ids = self.db.get_selected_shequ_ids()
            is_all_selected = self.db.is_all_shequ_selected()
            
            shequ_ids = None if is_all_selected else selected_ids
            await query.edit_message_text("✅ 设置已保存。\n正在获取对应第三方订单...")
            
            try:
                # 获取近两天的订单
                orders = self.order_api.get_recent_orders(days=2, shequ_ids=shequ_ids)
                
                if orders:
                    # 如果选择了特定第三方，只保存属于这些第三方的订单
                    if shequ_ids:
                        filtered_orders = [order for order in orders if order.get('ShequId', 0) in shequ_ids]
                        orders = filtered_orders
                    
                    # 保存订单到数据库
                    count = self.db.insert_orders_batch(orders)
                    
                    # 清理超过2天的订单
                    deleted_count = self.db.delete_expired_orders(days=2)
                    
                    # 如果选择了特定第三方，清理不属于这些第三方的订单
                    if shequ_ids:
                        cleanup_count = self.db.delete_orders_by_shequ_ids(shequ_ids)
                        if cleanup_count > 0:
                            print(f"已清理 {cleanup_count} 个不属于选中第三方的订单")
                    
                    success_msg = f"✅ 设置已保存。\n已获取对应第三方订单（共{count}条）"
                    await query.edit_message_text(success_msg)
                else:
                    await query.edit_message_text("✅ 设置已保存。\n已获取对应第三方订单（共0条）")
            except Exception as e:
                print(f"获取订单失败: {e}")
                import traceback
                traceback.print_exc()
                await query.edit_message_text(f"✅ 设置已保存。\n获取对应第三方订单失败：{str(e)}")
            
            return
        
        # 获取当前选中的第三方
        selected_ids = set(self.db.get_selected_shequ_ids())
        
        if data == "shequ_toggle_all":
            # 切换"全部"模式
            if len(selected_ids) == 0:
                # 当前是"全部"模式，不做任何操作
                await query.answer("当前已是'全部'模式")
            else:
                # 清除所有选择，切换到"全部"模式
                shequ_list = self.order_api.get_shequ_list()
                update_list = [{'Id': s.get('Id'), 'SName': s.get('SName', ''), 'is_selected': 0} for s in shequ_list]
            self.db.update_shequ_settings(update_list)
            await query.answer("已切换到'全部'模式")
            
            # 切换到全部模式时，不需要清理订单（因为要保留所有订单）
        else:
            # 切换单个第三方
            shequ_id = int(data.replace("shequ_toggle_", ""))
            
            # 获取第三方列表
            shequ_list = self.order_api.get_shequ_list()
            shequ_dict = {s.get('Id'): s for s in shequ_list}
            
            if shequ_id in selected_ids:
                # 取消选中
                selected_ids.remove(shequ_id)
            else:
                # 选中
                selected_ids.add(shequ_id)
            
            # 更新数据库
            update_list = []
            for s in shequ_list:
                update_list.append({
                    'Id': s.get('Id'),
                    'SName': s.get('SName', ''),
                    'is_selected': 1 if s.get('Id') in selected_ids else 0
                })
            self.db.update_shequ_settings(update_list)
            
            # 如果选择了特定第三方，清理不属于这些第三方的订单
            if selected_ids:
                # 确保转换为列表并都是整数类型
                selected_ids_list = [int(sid) for sid in selected_ids]
                deleted_count = self.db.delete_orders_by_shequ_ids(selected_ids_list)
                if deleted_count > 0:
                    print(f"切换分类后，已清理 {deleted_count} 个不属于选中第三方的订单")
        
        # 重新显示设置界面（两列布局）
        shequ_list = self.order_api.get_shequ_list()
        selected_ids = set(self.db.get_selected_shequ_ids())
        
        keyboard = []
        row = []
        for i, shequ in enumerate(shequ_list):
            shequ_id = shequ.get('Id')
            shequ_name = shequ.get('SName', f'第三方 {shequ_id}')
            is_selected = shequ_id in selected_ids
            
            # 添加选中标记：选中的显示 ✅，未选中的显示 ❌
            prefix = "✅ " if is_selected else "❌ "
            button_text = f"{prefix}{shequ_name}"
            
            row.append(InlineKeyboardButton(
                button_text,
                callback_data=f"shequ_toggle_{shequ_id}"
            ))
            
            # 每两个按钮一行，或者到达最后一个
            if len(row) == 2 or i == len(shequ_list) - 1:
                keyboard.append(row)
                row = []
        
        is_all_selected = len(selected_ids) == 0
        all_prefix = "✅ " if is_all_selected else "❌ "
        keyboard.append([InlineKeyboardButton(
            f"{all_prefix}全部（获取所有第三方）",
            callback_data="shequ_toggle_all"
        )])
        keyboard.append([InlineKeyboardButton(
            "✅ 完成设置",
            callback_data="shequ_done"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "请选择要获取订单的第三方：\n\n"
        if selected_ids:
            message_text += f"当前已选择 {len(selected_ids)} 个第三方\n"
        else:
            message_text += "当前设置为：获取全部第三方\n"
        message_text += "\n点击第三方名称可以切换选中状态\n点击'完成设置'保存配置"
        
        await query.edit_message_text(message_text, reply_markup=reply_markup)
    
    def run(self):
        """启动bot"""
        application = Application.builder().token(self.bot_token).build()
        
        # 添加命令处理器
        application.add_handler(CommandHandler("setshequ", self.handle_set_shequ_command))
        
        # 添加回调查询处理器
        application.add_handler(CallbackQueryHandler(self.handle_shequ_callback, pattern="^shequ_"))
        
        # 添加消息处理器
        message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        application.add_handler(message_handler)
        
        # 启动后台同步队列任务（如果可用）
        if application.job_queue is not None:
            application.job_queue.run_repeating(
                self.process_sync_queue,
                interval=self.sync_interval,
                first=self.sync_interval
            )
        else:
            print("警告: JobQueue 不可用，后台同步队列将不会自动轮询。")
        
        print("Telegram Bot 启动中...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def process_sync_queue(self, context: ContextTypes.DEFAULT_TYPE):
        """后台同步队列处理"""
        tasks = self.db.get_due_sync_tasks(self.sync_interval)
        if not tasks:
            return
        
        bot = context.bot
        for task in tasks:
            await self._process_single_sync_task(bot, task)

    async def _process_single_sync_task(self, bot, task: Dict):
        """执行单个同步任务"""
        order_id = task['order_id']
        attempts_before = task.get('attempts', 0)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] 后台同步订单 {order_id}，已尝试 {attempts_before} 次")
        
        try:
            result = self.order_api.sync_order(order_id, max_retries=1, retry_interval_min=0, retry_interval_max=0)
        except Exception as e:
            print(f"同步订单 {order_id} 异常: {e}")
            result = {'message': str(e)}
        
        order_detail = self.order_api.get_order_status_by_id(order_id)
        if order_detail:
            self.db.insert_order(order_detail)
        refund_status = self.order_api.extract_refund_status(order_detail)
        
        attempts = attempts_before + 1
        status_text = refund_status or (result.get('message') if isinstance(result, dict) else None)
        self.db.update_sync_task(order_id, attempts, int(time.time()), status_text)
        
        # 在后台输出当前状态信息
        ts_done = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if refund_status:
            print(f"[{ts_done}] 订单 {order_id} 当前状态: {refund_status}（同步第 {attempts} 次）")
        elif isinstance(result, dict) and result.get('success'):
            print(f"[{ts_done}] 订单 {order_id} 同步成功（第 {attempts} 次），状态未进入退单/退款。")
        else:
            msg = (result.get('message') if isinstance(result, dict) else "未知错误")
            print(f"[{ts_done}] 订单 {order_id} 同步失败（第 {attempts} 次），状态信息: {msg}")
        
        if refund_status:
            await self._notify_user(
                bot,
                task['chat_id'],
                task['message_id'],
                f"订单{refund_status}"
            )
            self.db.delete_sync_task(order_id)

    async def _notify_user(self, bot, chat_id: int, message_id: int, text: str):
        """向用户发送通知"""
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=message_id
            )
        except Exception as e:
            print(f"发送通知失败: {e}")
            await bot.send_message(chat_id=chat_id, text=text)

