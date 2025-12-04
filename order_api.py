import requests
import json
import time
import random
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import Config
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class OrderAPI:
    def __init__(self):
        self.base_url = Config.API_BASE_URL
        self.auth_token = Config.API_AUTHORIZATION_TOKEN
        self.cookie = Config.API_COOKIE
        self.page_size = Config.PAGE_SIZE
        
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-HK,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',
            'Authorization': self.auth_token,
            'Connection': 'keep-alive',
            'Referer': f'{self.base_url}/admin.html',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
        }
        
        self.cookies = {}
        if self.cookie:
            # 解析cookie字符串
            for item in self.cookie.split(';'):
                item = item.strip()
                if '=' in item:
                    key, value = item.split('=', 1)
                    self.cookies[key] = value
    
    def get_orders_page(self, page: int = 1, page_count: int = None, exp_time: int = 2, is_id: int = 1, shequ_id: int = None, max_retries: int = 10) -> Optional[Dict]:
        """获取指定页的订单列表（带重试机制）"""
        if page_count is None:
            page_count = self.page_size
        
        url = f'{self.base_url}/admin/orderList'
        params = {
            'Page': page,
            'PageCount': page_count,
            'ExpTime': exp_time,
            'IsId': is_id
        }
        
        # 如果指定了第三方ID，添加ShequId参数
        if shequ_id is not None:
            params['ShequId'] = shequ_id
        
        # 重试机制
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=self.headers,
                    cookies=self.cookies,
                    verify=False,  # 忽略SSL证书验证
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 递增等待时间：2秒、4秒、6秒...
                        print(f"获取订单失败: HTTP {response.status_code}，{wait_time}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        print(f"获取订单失败: HTTP {response.status_code}，已达到最大重试次数")
                        return None
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"获取订单异常: {e}，{wait_time}秒后重试 (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"获取订单异常: {e}，已达到最大重试次数")
                    return None
        
        return None
    
    def get_shequ_list(self) -> List[Dict]:
        """获取第三方列表"""
        url = f'{self.base_url}/admin/sheQuList'
        params = {
            'NotPage': 1
        }
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                cookies=self.cookies,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list):
                    return result
                elif isinstance(result, dict) and 'error' in result:
                    if result.get('error') == 0:
                        return result.get('info', [])
            return []
        except Exception as e:
            print(f"获取第三方列表异常: {e}")
            return []
    
    def _get_shequ_orders(self, shequ_id: Optional[int], days: int, cutoff_date, today_date) -> List[Dict]:
        """获取单个第三方的订单（内部方法，用于并行调用）"""
        orders = []
        page = 1
        shequ_name = f"第三方 {shequ_id}" if shequ_id else "全部"
        
        while True:
            result = self.get_orders_page(page=page, shequ_id=shequ_id)
            
            if not result:
                print(f"[{shequ_name}] 获取第 {page} 页失败，已重试10次，跳过该页继续")
                page += 1
                if page > 100:
                    break
                continue
            
            if result.get('error') != 0:
                print(f"[{shequ_name}] 获取第 {page} 页返回错误: {result.get('error')}")
                page += 1
                if page > 100:
                    break
                continue
            
            page_orders = result.get('info', [])
            if not page_orders:
                break
            
            # 过滤最近N天的订单
            recent_orders = []
            should_break = False
            for order in page_orders:
                create_at = order.get('CreateAt', 0)
                if create_at:
                    order_date = datetime.fromtimestamp(create_at).date()
                    if cutoff_date <= order_date <= today_date:
                        recent_orders.append(order)
                    elif order_date < cutoff_date:
                        should_break = True
                        break
            
            orders.extend(recent_orders)
            
            if should_break or len(page_orders) < self.page_size:
                break
            
            page += 1
        
        print(f"[{shequ_name}] 获取完成，共 {len(orders)} 个订单")
        return orders
    
    def get_recent_orders(self, days: int = 2, shequ_ids: List[int] = None) -> List[Dict]:
        """获取最近N天的订单（并行处理多个第三方）"""
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=days)).date()
        today_date = datetime.now().date()
        
        print(f"开始并行获取最近 {days} 天的订单（从 {cutoff_date} 到 {today_date}）...")
        
        # 如果没有指定第三方ID，获取全部
        if shequ_ids is None or len(shequ_ids) == 0:
            shequ_ids = [None]  # None表示获取全部
        
        all_orders = []
        
        # 使用线程池并行处理多个第三方
        with ThreadPoolExecutor(max_workers=min(len(shequ_ids), 10)) as executor:
            # 提交所有任务
            future_to_shequ = {
                executor.submit(self._get_shequ_orders, shequ_id, days, cutoff_date, today_date): shequ_id
                for shequ_id in shequ_ids
            }
            
            # 收集结果
            for future in as_completed(future_to_shequ):
                shequ_id = future_to_shequ[future]
                try:
                    orders = future.result()
                    all_orders.extend(orders)
                except Exception as e:
                    shequ_name = f"第三方 {shequ_id}" if shequ_id else "全部"
                    print(f"[{shequ_name}] 获取订单时发生异常: {e}")
        
        print(f"总共获取到 {len(all_orders)} 个最近 {days} 天的订单")
        return all_orders
    
    def get_all_today_orders(self) -> List[Dict]:
        """获取今天的所有订单（翻页直到获取完）- 已废弃，使用 get_recent_orders"""
        return self.get_recent_orders(days=1)
    
    def _get_shequ_new_orders(self, shequ_id: Optional[int], last_order_id: int, days: int, cutoff_date, today_date) -> List[Dict]:
        """获取单个第三方的新订单（内部方法，用于并行调用）"""
        new_orders = []
        page = 1
        
        while True:
            result = self.get_orders_page(page=page, shequ_id=shequ_id)
            
            if not result or result.get('error') != 0:
                break
            
            orders = result.get('info', [])
            if not orders:
                break
            
            # 过滤最近N天的订单和新订单
            found_new = False
            for order in orders:
                order_id = order.get('Id', 0)
                create_at = order.get('CreateAt', 0)
                
                if create_at:
                    order_date = datetime.fromtimestamp(create_at).date()
                    if cutoff_date <= order_date <= today_date and order_id > last_order_id:
                        new_orders.append(order)
                        found_new = True
                    elif order_date < cutoff_date or order_id <= last_order_id:
                        # 如果遇到更早的订单或已处理的订单，停止
                        return new_orders
            
            # 如果这一页的订单数量少于page_size，说明已经是最后一页
            if len(orders) < self.page_size:
                break
            
            page += 1
        
        return new_orders
    
    def get_new_orders(self, last_order_id: int = 0, days: int = 2, shequ_ids: List[int] = None) -> List[Dict]:
        """获取新订单（并行处理多个第三方）"""
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=days)).date()
        today_date = datetime.now().date()
        
        # 如果没有指定第三方ID，获取全部
        if shequ_ids is None or len(shequ_ids) == 0:
            shequ_ids = [None]
        
        all_new_orders = []
        
        # 使用线程池并行处理多个第三方
        with ThreadPoolExecutor(max_workers=min(len(shequ_ids), 10)) as executor:
            # 提交所有任务
            future_to_shequ = {
                executor.submit(self._get_shequ_new_orders, shequ_id, last_order_id, days, cutoff_date, today_date): shequ_id
                for shequ_id in shequ_ids
            }
            
            # 收集结果
            for future in as_completed(future_to_shequ):
                shequ_id = future_to_shequ[future]
                try:
                    orders = future.result()
                    all_new_orders.extend(orders)
                except Exception as e:
                    shequ_name = f"第三方 {shequ_id}" if shequ_id else "全部"
                    print(f"[{shequ_name}] 获取新订单时发生异常: {e}")
        
        return all_new_orders
    
    def get_order_detail(self, order_id: int) -> Optional[Dict]:
        """获取订单详情（通过订单列表API查找）"""
        # 通过订单列表API查找订单，使用较小的页面大小
        result = self.get_orders_page(page=1, page_count=100, is_id=1)
        if result and result.get('error') == 0:
            orders = result.get('info', [])
            for order in orders:
                if order.get('Id') == order_id:
                    return order
        return None
    
    def sync_order(self, order_id: int, max_retries: int = 10, retry_interval_min: int = 3, retry_interval_max: int = 5) -> Dict:
        """同步订单到系统（带重试机制，最多10次，每次间隔3-5分钟）
        
        返回:
            Dict: {
                'success': bool,  # 是否成功
                'attempt': int,   # 当前尝试次数
                'refund_status': str or None,  # 退单状态：'退单中'/'已退款'/'已退单' 或 None
                'message': str   # 状态消息
            }
        """
        url = f'{self.base_url}/admin/userTb'
        
        # 构建multipart/form-data
        boundary = '----WebKitFormBoundaryYeKFKujjIjw1wG6w'
        headers = self.headers.copy()
        headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        headers['Origin'] = self.base_url
        
        # 构建form data
        body = f'------WebKitFormBoundaryYeKFKujjIjw1wG6w\r\n'
        body += f'Content-Disposition: form-data; name="Id"\r\n\r\n'
        body += f'{order_id}\r\n'
        body += f'------WebKitFormBoundaryYeKFKujjIjw1wG6w--\r\n'
        
        # 重试机制：最多10次，每次间隔3-5分钟
        for attempt in range(max_retries):
            # 在每次同步前检查订单状态
            order_detail = self.get_order_detail(order_id)
            if order_detail:
                logs = order_detail.get('Logs', '')
                if isinstance(logs, str):
                    logs_lower = logs.lower()
                    # 检查退单状态
                    if '退单中' in logs_lower:
                        return {
                            'success': False,
                            'attempt': attempt + 1,
                            'refund_status': '退单中',
                            'message': '订单退单中'
                        }
                    elif '已退款' in logs_lower:
                        return {
                            'success': False,
                            'attempt': attempt + 1,
                            'refund_status': '已退款',
                            'message': '订单已退款'
                        }
                    elif '已退单' in logs_lower:
                        return {
                            'success': False,
                            'attempt': attempt + 1,
                            'refund_status': '已退单',
                            'message': '订单已退单'
                        }
            
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    cookies=self.cookies,
                    data=body.encode('utf-8'),
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('error') == 0:
                        print(f"订单 {order_id} 同步成功")
                        return {
                            'success': True,
                            'attempt': attempt + 1,
                            'refund_status': None,
                            'message': '同步成功'
                        }
                    else:
                        if attempt < max_retries - 1:
                            # 随机等待3-5分钟
                            wait_seconds = random.randint(retry_interval_min * 60, retry_interval_max * 60)
                            wait_minutes = wait_seconds / 60
                            print(f"订单 {order_id} 同步失败: {result}，{wait_minutes:.1f}分钟后重试 (尝试 {attempt + 1}/{max_retries})")
                            time.sleep(wait_seconds)
                        else:
                            print(f"订单 {order_id} 同步失败: {result}，已达到最大重试次数")
                            return {
                                'success': False,
                                'attempt': attempt + 1,
                                'refund_status': None,
                                'message': '同步失败，已达到最大重试次数'
                            }
                else:
                    if attempt < max_retries - 1:
                        wait_seconds = random.randint(retry_interval_min * 60, retry_interval_max * 60)
                        wait_minutes = wait_seconds / 60
                        print(f"订单 {order_id} 同步失败: HTTP {response.status_code}，{wait_minutes:.1f}分钟后重试 (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(wait_seconds)
                    else:
                        print(f"订单 {order_id} 同步失败: HTTP {response.status_code}，已达到最大重试次数")
                        return {
                            'success': False,
                            'attempt': attempt + 1,
                            'refund_status': None,
                            'message': f'同步失败: HTTP {response.status_code}'
                        }
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_seconds = random.randint(retry_interval_min * 60, retry_interval_max * 60)
                    wait_minutes = wait_seconds / 60
                    print(f"同步订单 {order_id} 异常: {e}，{wait_minutes:.1f}分钟后重试 (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(wait_seconds)
                else:
                    print(f"同步订单 {order_id} 异常: {e}，已达到最大重试次数")
                    return {
                        'success': False,
                        'attempt': attempt + 1,
                        'refund_status': None,
                        'message': f'同步异常: {str(e)}'
                    }
        
        return {
            'success': False,
            'attempt': max_retries,
            'refund_status': None,
            'message': '同步失败'
        }
    
    def get_order_status_by_id(self, order_id: int) -> Optional[Dict]:
        """根据订单ID获取订单状态"""
        url = f'{self.base_url}/admin/orderList'
        params = {
            'Page': 1,
            'PageCount': 10,
            'ExpTime': 2,
            'Id': order_id
        }
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=self.headers,
                cookies=self.cookies,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('error') == 0:
                    info = result.get('info', [])
                    if info:
                        return info[0]
            else:
                print(f"获取订单 {order_id} 状态失败: HTTP {response.status_code}")
        except Exception as e:
            print(f"获取订单 {order_id} 状态异常: {e}")
        return None
    
    def extract_refund_status(self, order_detail: Optional[Dict]) -> Optional[str]:
        """从订单详情中提取退单状态"""
        if not order_detail:
            return None
        
        keywords = ['退单中', '已退款', '已退单']
        logs = order_detail.get('Logs') or order_detail.get('logs')
        
        log_entries = []
        if isinstance(logs, str):
            try:
                log_entries = json.loads(logs)
            except Exception:
                # 日志可能是普通字符串
                for keyword in keywords:
                    if keyword in logs:
                        return keyword
        elif isinstance(logs, list):
            log_entries = logs
        
        for entry in reversed(log_entries):
            content = entry.get('content', '') if isinstance(entry, dict) else str(entry)
            for keyword in keywords:
                if keyword in content:
                    return keyword
        
        # 如果Logs没有包含目标状态，尝试检查OrderStatus或其他字段
        order_status_text = order_detail.get('OrderStatusText') or order_detail.get('order_status_text')
        if order_status_text:
            for keyword in keywords:
                if keyword in order_status_text:
                    return keyword
        
        return None

