import sqlite3
import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from config import Config

class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """初始化数据库表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 创建订单表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                order_id INTEGER UNIQUE NOT NULL,
                create_at INTEGER,
                user_name TEXT,
                user_id INTEGER,
                goods_id INTEGER,
                goods_name TEXT,
                order_sn TEXT,
                other_order_sn TEXT,
                order_status INTEGER,
                order_amount TEXT,
                price TEXT,
                params TEXT,
                douyin_url TEXT,
                logs TEXT,
                created_date TEXT,
                shequ_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 如果表已存在但没有 shequ_id 字段，添加该字段
        try:
            cursor.execute('ALTER TABLE orders ADD COLUMN shequ_id INTEGER')
        except sqlite3.OperationalError:
            # 字段已存在，忽略错误
            pass
        
        # 创建索引以提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_douyin_url ON orders(douyin_url)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_order_id ON orders(order_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_date ON orders(created_date)
        ''')
        
        # 创建同步任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_sync_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER UNIQUE NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER,
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 0,
                last_synced_at INTEGER DEFAULT 0,
                douyin_url TEXT,
                shequ_id INTEGER,
                order_sn TEXT,
                status_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sync_last_synced_at ON order_sync_tasks(last_synced_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sync_attempts ON order_sync_tasks(attempts)
        ''')
        
        # 创建第三方设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shequ_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shequ_id INTEGER UNIQUE NOT NULL,
                shequ_name TEXT,
                is_selected INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_shequ_selected ON shequ_settings(is_selected)
        ''')
        
        conn.commit()
        conn.close()
    
    def extract_douyin_url(self, params: str) -> Optional[str]:
        """从Params JSON字符串中提取抖音链接"""
        try:
            params_list = json.loads(params)
            for param in params_list:
                if isinstance(param, dict):
                    value = param.get('value', '')
                    if 'v.douyin.com' in value:
                        # 提取完整的抖音链接
                        url = value.strip()
                        # 确保URL完整
                        if not url.startswith('http'):
                            continue
                        # 标准化URL格式
                        return self.normalize_url(url)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return None
    
    def insert_order(self, order: Dict) -> bool:
        """插入或更新订单"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 提取抖音链接
            params = order.get('Params', '[]')
            douyin_url = self.extract_douyin_url(params)
            
            # 获取创建日期（用于过滤今天的订单）
            create_at = order.get('CreateAt', 0)
            if create_at:
                created_date = datetime.fromtimestamp(create_at).strftime('%Y-%m-%d')
            else:
                created_date = datetime.now().strftime('%Y-%m-%d')
            
            cursor.execute('''
                INSERT OR REPLACE INTO orders (
                    order_id, create_at, user_name, user_id, goods_id, goods_name,
                    order_sn, other_order_sn, order_status, order_amount, price,
                    params, douyin_url, logs, created_date, shequ_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                order.get('Id'),
                create_at,
                order.get('UserName', ''),
                order.get('UserId', 0),
                order.get('GoodsId', 0),
                order.get('GoodsName', ''),
                order.get('OrderSN', ''),
                order.get('OtherOrderSN', ''),
                order.get('OrderStatus', 0),
                order.get('OrderAmount', '0'),
                order.get('Price', '0'),
                params,
                douyin_url,
                order.get('Logs', '[]'),
                created_date,
                order.get('ShequId', 0)
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"插入订单失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def insert_orders_batch(self, orders: List[Dict]) -> int:
        """批量插入订单（跳过已存在的订单）"""
        count = 0
        skipped = 0
        for order in orders:
            order_id = order.get('Id', 0)
            # 检查订单是否已存在
            if self.order_exists(order_id):
                skipped += 1
                continue
            if self.insert_order(order):
                count += 1
        if skipped > 0:
            print(f"跳过 {skipped} 个已存在的订单")
        return count
    
    def normalize_url(self, url: str) -> str:
        """标准化URL格式用于匹配"""
        if not url:
            return ''
        url = url.strip()
        # 移除尾部斜杠
        url = url.rstrip('/')
        # 确保以/结尾（用于匹配）
        if 'v.douyin.com' in url:
            if not url.endswith('/'):
                url += '/'
        return url
    
    def find_order_by_douyin_url(self, url: str) -> Optional[Dict]:
        """根据抖音链接查找订单"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 清理和标准化URL
            clean_url = self.normalize_url(url)
            if not clean_url or not clean_url.startswith('http'):
                return None
            
            # 提取URL的核心部分（去掉协议和尾部斜杠）
            url_core = clean_url.replace('https://', '').replace('http://', '').rstrip('/')
            
            # 使用LIKE匹配，支持多种URL格式
            cursor.execute('''
                SELECT order_id, create_at, user_name, user_id, goods_id, goods_name,
                       order_sn, other_order_sn, order_status, order_amount, price,
                       params, douyin_url, logs, created_date, shequ_id
                FROM orders
                WHERE douyin_url = ? 
                   OR douyin_url = ?
                   OR douyin_url LIKE ?
                   OR douyin_url LIKE ?
                ORDER BY create_at DESC
                LIMIT 1
            ''', (
                clean_url,
                clean_url.rstrip('/'),
                f'%{url_core}%',
                f'%{url_core}/%'
            ))
            
            row = cursor.fetchone()
            if row:
                return {
                    'order_id': row[0],
                    'create_at': row[1],
                    'user_name': row[2],
                    'user_id': row[3],
                    'goods_id': row[4],
                    'goods_name': row[5],
                    'order_sn': row[6],
                    'other_order_sn': row[7],
                    'order_status': row[8],
                    'order_amount': row[9],
                    'price': row[10],
                    'params': row[11],
                    'douyin_url': row[12],
                    'logs': row[13],
                    'created_date': row[14],
                    'shequ_id': row[15] if len(row) > 15 else 0
                }
            return None
        except Exception as e:
            print(f"查询订单失败: {e}")
            return None
        finally:
            conn.close()
    
    def get_today_orders_count(self) -> int:
        """获取今天已存储的订单数量"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('SELECT COUNT(*) FROM orders WHERE created_date = ?', (today,))
            return cursor.fetchone()[0]
        except Exception as e:
            print(f"查询订单数量失败: {e}")
            return 0
        finally:
            conn.close()
    
    def order_exists(self, order_id: int) -> bool:
        """检查订单是否已存在"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT 1 FROM orders WHERE order_id = ? LIMIT 1', (order_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"检查订单失败: {e}")
            return False
        finally:
            conn.close()
    
    def get_order_status(self, order_id: int) -> Optional[Dict]:
        """获取订单状态信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT order_status, logs
                FROM orders
                WHERE order_id = ?
            ''', (order_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'order_status': row[0],
                    'logs': row[1]
                }
            return None
        except Exception as e:
            print(f"获取订单状态失败: {e}")
            return None
        finally:
            conn.close()
    
    def is_refund_status(self, order: Dict) -> bool:
        """检查订单是否是退单相关状态"""
        # 检查logs中是否包含退单相关关键词
        logs = order.get('logs', '')
        if isinstance(logs, str):
            logs_lower = logs.lower()
            refund_keywords = ['退单中', '已退款', '已退单', '退款中', '退单']
            for keyword in refund_keywords:
                if keyword in logs_lower:
                    print(f"检测到退单关键词: {keyword}")
                    return True
        
        # 检查order_status字段（如果状态值是特定的数字）
        # 根据实际API返回的状态值来调整
        order_status = order.get('order_status', 0)
        # 常见的退单状态值可能是负数或特定数字，根据实际情况调整
        # 如果order_status是负数，可能是退单状态
        if order_status and order_status < 0:
            print(f"检测到退单状态码: {order_status}")
            return True
        
        return False
    
    def get_selected_shequ_ids(self) -> List[int]:
        """获取选中的第三方ID列表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT shequ_id FROM shequ_settings WHERE is_selected = 1')
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            print(f"获取选中的第三方失败: {e}")
            return []
        finally:
            conn.close()
    
    def is_all_shequ_selected(self) -> bool:
        """检查是否选择了全部（没有选中任何第三方或全部取消选中）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT COUNT(*) FROM shequ_settings WHERE is_selected = 1')
            count = cursor.fetchone()[0]
            return count == 0  # 如果没有选中任何第三方，则获取全部
        except Exception as e:
            print(f"检查第三方设置失败: {e}")
            return True  # 默认获取全部
        finally:
            conn.close()
    
    def update_shequ_settings(self, shequ_list: List[Dict]):
        """更新第三方设置"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 先清除所有设置
            cursor.execute('UPDATE shequ_settings SET is_selected = 0')
            
            # 更新或插入新的设置
            for shequ in shequ_list:
                cursor.execute('''
                    INSERT OR REPLACE INTO shequ_settings (shequ_id, shequ_name, is_selected, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    shequ.get('Id'),
                    shequ.get('SName', ''),
                    shequ.get('is_selected', 0)
                ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"更新第三方设置失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def add_sync_task(self, order_id: int, chat_id: int, message_id: int, *,
                      initial_attempts: int = 0, max_attempts: int = 0,
                      douyin_url: str = '', shequ_id: int = 0, order_sn: str = '') -> bool:
        """添加或更新同步任务"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            now = int(time.time())
            last_synced_at = now if initial_attempts > 0 else 0
            # 由于部分系统SQLite版本较老，不支持 ON CONFLICT 语法，这里改为“先查再更新/插入”的方式
            cursor.execute('SELECT 1 FROM order_sync_tasks WHERE order_id = ?', (order_id,))
            exists = cursor.fetchone() is not None

            if exists:
                # 更新已有任务（重置 attempts/last_synced_at 等）
                cursor.execute('''
                    UPDATE order_sync_tasks
                    SET chat_id = ?,
                        message_id = ?,
                        attempts = ?,
                        max_attempts = ?,
                        last_synced_at = ?,
                        douyin_url = ?,
                        shequ_id = ?,
                        order_sn = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                ''', (
                    chat_id,
                    message_id,
                    initial_attempts,
                    max_attempts,
                    last_synced_at,
                    douyin_url,
                    shequ_id,
                    order_sn,
                    order_id,
                ))
            else:
                # 新建任务
                cursor.execute('''
                    INSERT INTO order_sync_tasks (
                        order_id, chat_id, message_id, attempts, max_attempts,
                        last_synced_at, douyin_url, shequ_id, order_sn, status_text, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, CURRENT_TIMESTAMP)
                ''', (
                    order_id,
                    chat_id,
                    message_id,
                    initial_attempts,
                    max_attempts,
                    last_synced_at,
                    douyin_url,
                    shequ_id,
                    order_sn,
                ))
            conn.commit()
            return True
        except Exception as e:
            print(f"添加同步任务失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_sync_task(self, order_id: int) -> Optional[Dict]:
        """获取同步任务"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT order_id, chat_id, message_id, attempts, max_attempts,
                       last_synced_at, douyin_url, shequ_id, order_sn, status_text
                FROM order_sync_tasks
                WHERE order_id = ?
            ''', (order_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'order_id': row[0],
                    'chat_id': row[1],
                    'message_id': row[2],
                    'attempts': row[3],
                    'max_attempts': row[4],
                    'last_synced_at': row[5],
                    'douyin_url': row[6],
                    'shequ_id': row[7],
                    'order_sn': row[8],
                    'status_text': row[9]
                }
            return None
        except Exception as e:
            print(f"获取同步任务失败: {e}")
            return None
        finally:
            conn.close()
    
    def get_due_sync_tasks(self, interval_seconds: int) -> List[Dict]:
        """获取到期需要同步的任务"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            threshold = int(time.time()) - interval_seconds
            cursor.execute('''
                SELECT order_id, chat_id, message_id, attempts, max_attempts,
                       last_synced_at, douyin_url, shequ_id, order_sn, status_text
                FROM order_sync_tasks
                WHERE last_synced_at IS NULL OR last_synced_at = 0 OR last_synced_at <= ?
            ''', (threshold,))
            rows = cursor.fetchall()
            tasks = []
            for row in rows:
                tasks.append({
                    'order_id': row[0],
                    'chat_id': row[1],
                    'message_id': row[2],
                    'attempts': row[3],
                    'max_attempts': row[4],
                    'last_synced_at': row[5],
                    'douyin_url': row[6],
                    'shequ_id': row[7],
                    'order_sn': row[8],
                    'status_text': row[9]
                })
            return tasks
        except Exception as e:
            print(f"获取需要同步的任务失败: {e}")
            return []
        finally:
            conn.close()
    
    def update_sync_task(self, order_id: int, attempts: int, last_synced_at: int, status_text: Optional[str] = None):
        """更新同步任务状态"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE order_sync_tasks
                SET attempts = ?, last_synced_at = ?, status_text = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (attempts, last_synced_at, status_text, order_id))
            conn.commit()
        except Exception as e:
            print(f"更新同步任务失败: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def delete_sync_task(self, order_id: int):
        """删除同步任务"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM order_sync_tasks WHERE order_id = ?', (order_id,))
            conn.commit()
        except Exception as e:
            print(f"删除同步任务失败: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def delete_expired_orders(self, days: int = 2):
        """删除超过指定天数的订单"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # 确保参数是字符串类型
            cursor.execute('DELETE FROM orders WHERE created_date < ?', (str(cutoff_date),))
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                print(f"已删除 {deleted_count} 个超过 {days} 天的订单")
            
            return deleted_count
        except Exception as e:
            print(f"删除过期订单失败: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return 0
        finally:
            conn.close()
    
    def delete_orders_by_shequ_ids(self, exclude_shequ_ids: List[int]):
        """删除不属于指定第三方ID列表的订单"""
        if not exclude_shequ_ids:
            return 0
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 确保所有ID都是整数类型
            exclude_shequ_ids = [int(sid) for sid in exclude_shequ_ids]
            
            # 构建占位符和参数元组
            placeholders = ','.join(['?'] * len(exclude_shequ_ids))
            # 将列表转换为元组传递给execute
            cursor.execute(f'DELETE FROM orders WHERE shequ_id NOT IN ({placeholders})', tuple(exclude_shequ_ids))
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                print(f"已删除 {deleted_count} 个不属于选中第三方的订单")
            
            return deleted_count
        except Exception as e:
            print(f"删除订单失败: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return 0
        finally:
            conn.close()

