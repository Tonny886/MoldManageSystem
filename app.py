import os
from dotenv import load_dotenv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, send_from_directory, url_for, session
import json
import hashlib
from functools import wraps
import socket
from supabase import create_client, Client
import atexit
import logging

# ========== 配置日志 ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# 加载环境变量
load_dotenv()

# 创建 Flask 应用
app = Flask(__name__,
    static_folder='static',
    static_url_path='/static',
    template_folder='templates'
)
app.secret_key = os.getenv('SECRET_KEY', 'manufacturer-system-secret-key-2024')

# 修复会话配置
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800
)
# ========== 新增：防止休眠配置 ==========
class AntiSleepManager:
    """防止应用休眠的管理器"""
    
    def __init__(self, app):
        self.app = app
        self.is_active = False
        self.wakeup_thread = None
        self.last_activity = datetime.now()
        self.self_wakeup_url = os.getenv('SELF_WAKEUP_URL')
        self.external_ping_urls = [
            "https://api.uptimerobot.com/v2/getMonitors",  # 仅示例，需要配置
            "https://hc-ping.com/"  # Healthchecks.io 服务
        ]
        
        # 读取平台特定配置
        self.platform = os.getenv('PLATFORM', 'unknown').lower()
        self.wakeup_interval = int(os.getenv('WAKEUP_INTERVAL', '300'))  # 默认5分钟
        
    def start(self):
        """启动防休眠机制"""
        if self.is_active:
            return
            
        self.is_active = True
        
        # 方法1：内部定时自唤醒
        if self.self_wakeup_url:
            self._start_self_wakeup()
            logger.info(f"✅ 启动自唤醒机制，间隔: {self.wakeup_interval}秒")
        
        # 方法2：记录活跃时间
        self._start_activity_tracker()
        
        # 方法3：平台特定优化
        self._apply_platform_optimizations()
        
        logger.info("🚀 防休眠管理器已启动")
    
    def _start_self_wakeup(self):
        """启动自我唤醒线程"""
        def wakeup_worker():
            while self.is_active:
                try:
                    # 等待间隔时间
                    time.sleep(self.wakeup_interval)
                    
                    # 检查是否需要唤醒
                    idle_time = (datetime.now() - self.last_activity).seconds
                    if idle_time > self.wakeup_interval:
                        self._perform_self_wakeup()
                        
                except Exception as e:
                    logger.error(f"❌ 自唤醒线程错误: {e}")
                    time.sleep(60)  # 出错后等待1分钟
        
        self.wakeup_thread = threading.Thread(
            target=wakeup_worker,
            daemon=True,
            name="WakeupThread"
        )
        self.wakeup_thread.start()
    
    def _perform_self_wakeup(self):
        """执行自我唤醒"""
        try:
            # 尝试多种唤醒方式
            
            # 方式1：直接请求健康检查端点
            if self.self_wakeup_url:
                response = requests.get(
                    f"{self.self_wakeup_url}/health",
                    timeout=10,
                    headers={'User-Agent': 'Wakeup-Bot/1.0'}
                )
                logger.info(f"🔔 自唤醒请求: {response.status_code}")
            
            # 方式2：执行轻量级数据库查询
            self._perform_keepalive_query()
            
            # 方式3：更新最后活动时间
            self.last_activity = datetime.now()
            
        except requests.RequestException as e:
            logger.warning(f"⚠️ 自唤醒失败: {e}")
        except Exception as e:
            logger.error(f"❌ 自唤醒异常: {e}")
    
    def _perform_keepalive_query(self):
        """执行保持连接查询"""
        try:
            # 简单的 Supabase 查询保持连接活跃
            client = get_client()
            if client:
                # 执行一个简单的查询
                client.select('users', {'limit': '1'})
                logger.debug("✅ 保持连接查询成功")
        except Exception as e:
            logger.debug(f"保持连接查询失败: {e}")
    
    def _start_activity_tracker(self):
        """启动活动跟踪"""
        @self.app.before_request
        def track_activity():
            self.last_activity = datetime.now()
    
    def _apply_platform_optimizations(self):
        """应用平台特定的优化"""
        platform_optimizations = {
            'render': self._optimize_for_render,
            'heroku': self._optimize_for_heroku,
            'railway': self._optimize_for_railway,
            'vercel': self._optimize_for_vercel,
        }
        
        if self.platform in platform_optimizations:
            platform_optimizations[self.platform]()
    
    def _optimize_for_render(self):
        """Render.com 平台优化"""
        logger.info("🎯 应用 Render.com 优化配置")
        # Render 免费版30分钟休眠，建议设置25分钟唤醒
        self.wakeup_interval = min(self.wakeup_interval, 1500)  # 25分钟
    
    def _optimize_for_heroku(self):
        """Heroku 平台优化"""
        logger.info("🎯 应用 Heroku 优化配置")
        # Heroku 免费版30分钟休眠
        self.wakeup_interval = min(self.wakeup_interval, 1500)  # 25分钟
    
    def _optimize_for_railway(self):
        """Railway 平台优化"""
        logger.info("🎯 应用 Railway 优化配置")
        # Railway 5分钟无活动停止
        self.wakeup_interval = min(self.wakeup_interval, 240)  # 4分钟
    
    def _optimize_for_vercel(self):
        """Vercel 平台优化"""
        logger.info("🎯 应用 Vercel 优化配置")
        # Vercel 无服务器函数，无需特殊处理
    
    def stop(self):
        """停止防休眠机制"""
        self.is_active = False
        if self.wakeup_thread:
            self.wakeup_thread.join(timeout=5)
        logger.info("🛑 防休眠管理器已停止")

# 初始化防休眠管理器
anti_sleep = AntiSleepManager(app)


# Supabase 配置
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# 用户角色定义
USER_ROLES = {
    'super_admin': '超级管理员',
    'manufacturer_admin': '厂家管理员', 
    'user': '普通用户'
}

# 全局客户端变量
client = None

def get_client():
    """获取 Supabase 客户端（延迟初始化）"""
    global client
    if client is None:
        try:
            client = SupabaseClient()
            print("✅ Supabase 客户端已初始化")
        except Exception as e:
            print(f"❌ Supabase 初始化失败: {e}")
            client = None
    return client
# ========== 新增：连接池和重试机制 ==========
class ConnectionManager:
    """数据库连接管理器"""
    
    def __init__(self):
        self.retry_count = 0
        self.max_retries = 3
        self.retry_delay = 5  # 秒
    
    def ensure_connection(self):
        """确保数据库连接正常"""
        global client
        
        for attempt in range(self.max_retries):
            try:
                if client is None:
                    client = get_client()
                
                # 测试连接
                test_result = client.select('users', {'limit': '1'})
                if test_result['error']:
                    raise Exception(f"连接测试失败: {test_result['error']}")
                
                self.retry_count = 0
                logger.debug("✅ 数据库连接正常")
                return True
                
            except Exception as e:
                self.retry_count += 1
                logger.warning(f"⚠️ 数据库连接失败 ({attempt+1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    client = None  # 重置客户端
                else:
                    logger.error("❌ 数据库连接彻底失败")
                    return False
        
        return False

connection_manager = ConnectionManager()

# ========== 修改：增强的初始化函数 ==========
def init_app():
    """增强的应用初始化"""
    try:
        # 启动防休眠机制
        anti_sleep.start()
        
        # 确保数据库连接
        if not connection_manager.ensure_connection():
            logger.error("❌ 数据库连接初始化失败")
            return False
            
        # 初始化数据
        if client:
            init_supabase_data()
            logger.info("✅ 厂家保养人员管理系统初始化完成")
            
            # 执行一次初始唤醒
            anti_sleep._perform_self_wakeup()
            
            return True
            
    except Exception as e:
        logger.error(f"❌ 应用初始化失败: {e}")
        return False
# ========== 新增：快速恢复中间件 ==========
@app.before_request
def before_request():
    """请求前处理 - 包含快速恢复机制"""
    try:
        # 记录活动时间
        anti_sleep.last_activity = datetime.now()
        
        # 检查并恢复数据库连接
        if not client:
            connection_manager.ensure_connection()
            
    except Exception as e:
        logger.error(f"❌ 请求前处理失败: {e}")

@app.context_processor
def inject_user_roles():
    return dict(user_roles=USER_ROLES)

def get_local_ip():
    """获取本机IP地址（简化版）"""
    return request.host_url.rstrip('/')

def generate_qr_code(url):
    """二维码生成占位函数（已移除功能）"""
    return None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

class SupabaseClient:
    """Supabase 数据客户端"""
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise Exception("Supabase 环境变量未设置")
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    def select(self, table, filters=None):
        try:
            query = self.client.table(table).select("*")
            
            if filters:
                for key, value in filters.items():
                    if key == 'manufacturer_id' and value.startswith('eq.'):
                        manufacturer_id = value[3:]
                        query = query.eq('manufacturer_id', manufacturer_id)
                    elif key == 'is_active' and value == 'eq.true':
                        query = query.eq('is_active', True)
                    elif key == 'username' and value.startswith('eq.'):
                        username = value[3:]
                        query = query.eq('username', username)
                    elif key == 'id' and value.startswith('eq.'):
                        item_id = int(value[3:])
                        query = query.eq('id', item_id)
            
            response = query.execute()
            data = response.data
            
            if filters and 'limit' in filters:
                limit = int(filters['limit'])
                data = data[:limit]
                
            return {'data': data, 'error': None}
            
        except Exception as e:
            print(f"❌ Supabase 查询错误 ({table}): {e}")
            return {'data': [], 'error': str(e)}
    
    def insert(self, table, data):
        try:
            data['created_at'] = datetime.now().isoformat()
            if table == 'maintenance_personnel':
                data['updated_at'] = datetime.now().isoformat()
                if 'is_active' not in data:
                    data['is_active'] = True
            
            response = self.client.table(table).insert(data).execute()
            
            if response.data:
                return {'data': response.data, 'error': None}
            else:
                return {'data': None, 'error': '插入失败'}
                
        except Exception as e:
            print(f"❌ Supabase 插入错误 ({table}): {e}")
            return {'data': None, 'error': str(e)}
    
    def update(self, table, data, filters=None):
        try:
            query = self.client.table(table)
            
            if filters:
                for key, value in filters.items():
                    if key == 'id' and value.startswith('eq.'):
                        item_id = int(value[3:])
                        query = query.eq('id', item_id)
                    elif key == 'manufacturer_id' and value.startswith('eq.'):
                        manufacturer_id = value[3:]
                        query = query.eq('manufacturer_id', manufacturer_id)
            
            if table == 'maintenance_personnel':
                data['updated_at'] = datetime.now().isoformat()
            
            response = query.update(data).execute()
            
            if response.data:
                return {'data': response.data, 'error': None}
            else:
                return {'data': None, 'error': '更新失败，未找到记录'}
                
        except Exception as e:
            print(f"❌ Supabase 更新错误 ({table}): {e}")
            return {'data': None, 'error': str(e)}

def ensure_admin_user():
    try:
        client = get_client()
        if not client:
            return False
            
        user_response = client.select('users', {'username': 'eq.admin'})
        admin_exists = len(user_response['data']) > 0
        
        if not admin_exists:
            print("⚠️ 未找到管理员用户，正在创建...")
            admin_user = {
                'username': 'admin',
                'password': hash_password('admin123'),
                'real_name': '系统管理员',
                'role': 'super_admin',
                'manufacturer_id': None,
                'email': 'admin@example.com',
                'phone': '13800138000',
                'is_active': True,
                'created_by': 'system'
            }
            
            response = client.insert('users', admin_user)
            
            if response['error']:
                print(f"❌ 创建管理员用户失败: {response['error']}")
                return False
            else:
                print("✅ 管理员用户创建成功")
                return True
        else:
            print("✅ 管理员用户已存在")
            return True
            
    except Exception as e:
        print(f"❌ 确保管理员用户存在时出错: {e}")
        return False

def init_supabase_data():
    try:
        client = get_client()
        if not client:
            return False
            
        manufacturers_response = client.select('manufacturers', {'limit': '1'})
        
        if not manufacturers_response['data']:
            print("📁 创建示例厂家数据...")
            example_manufacturer = {
                'manufacturer_id': 'TEST001',
                'name': '示例厂家',
                'contact_person': '张经理',
                'phone': '13800138000',
                'email': 'test@example.com'
            }
            
            result = client.insert('manufacturers', example_manufacturer)
            if not result['error']:
                print("✅ 示例厂家创建成功")
        
        return ensure_admin_user()
        
    except Exception as e:
        print(f"❌ 初始化 Supabase 数据失败: {e}")
        return False

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if client is None:
                init_app()
                
            if 'user' not in session:
                return redirect(url_for('login'))
            
            if role and session['user']['role'] not in role:
                return render_template('error.html', 
                    error="权限不足", 
                    message="您没有访问此页面的权限"), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.before_request
def before_request():
    if client is None:
        init_app()

# ========== 修正后的路由定义开始 ==========

@app.route('/')
def home():
    """根路径重定向"""
    # 如果用户已登录，重定向到首页
    if 'user' in session:
        return redirect(url_for('index'))
    # 否则重定向到登录页
    else:
        return redirect(url_for('login'))

# ========== 增强的健康检查端点 ==========
@app.route('/health')
def health():
    """增强的健康检查端点"""
    try:
        # 基础状态检查
        db_status = "connected" if client else "disconnected"
        
        # 尝试数据库连接测试
        db_test_result = "unknown"
        if client:
            test_response = client.select('users', {'limit': '1'})
            db_test_result = "healthy" if not test_response['error'] else "unhealthy"
        
        # 收集系统信息
        system_info = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "connection": db_status,
                "test": db_test_result
            },
            "anti_sleep": {
                "active": anti_sleep.is_active,
                "last_activity": anti_sleep.last_activity.isoformat(),
                "idle_seconds": (datetime.now() - anti_sleep.last_activity).seconds,
                "platform": anti_sleep.platform,
                "wakeup_interval": anti_sleep.wakeup_interval
            },
            "memory": {
                "threads": threading.active_count()
            }
        }
        
        logger.info(f"🔍 健康检查请求 - 状态: {system_info['status']}")
        
        return jsonify(system_info)
        
    except Exception as e:
        logger.error(f"❌ 健康检查失败: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500
# ========== 新增：专门的外部队列唤醒端点 ==========
@app.route('/wakeup', methods=['GET', 'POST'])
def wakeup():
    """外部唤醒端点 - 用于监控服务调用"""
    try:
        # 验证唤醒密钥（可选）
        wakeup_key = request.args.get('key') or request.form.get('key')
        expected_key = os.getenv('WAKEUP_KEY')
        
        if expected_key and wakeup_key != expected_key:
            return jsonify({
                "status": "error",
                "message": "无效的唤醒密钥"
            }), 401
        
        # 执行唤醒操作
        anti_sleep.last_activity = datetime.now()
        
        # 执行数据库保持连接
        anti_sleep._perform_keepalive_query()
        
        # 记录唤醒日志
        logger.info(f"🔔 外部唤醒请求 - 来源: {request.remote_addr}")
        
        return jsonify({
            "status": "success",
            "message": "应用已唤醒",
            "timestamp": datetime.now().isoformat(),
            "next_wakeup": (datetime.now() + timedelta(seconds=anti_sleep.wakeup_interval)).isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ 唤醒端点错误: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# ========== 新增：状态监控端点 ==========
@app.route('/status')
@login_required(role=['super_admin'])
def system_status():
    """简化版系统状态页面"""
    try:
        # 基本状态信息
        status_info = {
            "应用状态": "运行中",
            "数据库连接": "正常" if client else "断开",
            "最后活动": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "用户角色": session.get('user', {}).get('role', '未知')
        }
        
        # 添加防休眠信息（如果可用）
        if hasattr(anti_sleep, 'is_active'):
            status_info["防休眠状态"] = "运行中" if anti_sleep.is_active else "已停止"
            status_info["平台"] = getattr(anti_sleep, 'platform', '未知')
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return render_template('status.html',
                             status_info=status_info,
                             current_time=current_time,
                             user=session.get('user'))
                             
    except Exception as e:
        return render_template('error.html',
                             error="状态页面错误",
                             message=str(e),
                             user=session.get('user'))

# ========== 新增：清理和退出处理 ==========
def cleanup_on_exit():
    """应用退出时的清理工作"""
    logger.info("🛑 应用正在关闭...")
    anti_sleep.stop()
    logger.info("✅ 清理完成")

# 注册退出处理
atexit.register(cleanup_on_exit)

@app.route('/logout')
def logout():
    """用户退出登录"""
    username = session.get('user', {}).get('username', '未知用户')
    session.pop('user', None)
    print(f"✅ 用户 {username} 已退出登录")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            return render_template('login.html', error='请输入用户名和密码')
        
        try:
            client = get_client()
            if not client:
                return render_template('login.html', error='数据库连接失败，请稍后重试')
            
            user_response = client.select('users', {'username': f'eq.{username}'})
            
            if not user_response['data']:
                return render_template('login.html', error='用户名或密码错误')
            
            user = user_response['data'][0]
            
            if not user.get('is_active', True):
                return render_template('login.html', error='用户已被禁用，请联系管理员')
            
            input_password_hash = hash_password(password)
            stored_password_hash = user['password']
            
            if stored_password_hash != input_password_hash:
                return render_template('login.html', error='用户名或密码错误')
            
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'real_name': user['real_name'],
                'role': user['role'],
                'manufacturer_id': user.get('manufacturer_id')
            }
            
            return redirect(url_for('index'))
                
        except Exception as e:
            print(f"❌ 登录错误: {e}")
            return render_template('login.html', error='系统错误，请稍后重试')
    
    return render_template('login.html')

@app.route('/index')
@login_required()
def index():
    """系统首页"""
    try:
        # 验证用户会话
        user = session.get('user')
        if not user:
            return redirect(url_for('login'))
            
        current_url = request.host_url.rstrip('/')
        
        # 简化首页数据，避免复杂逻辑
        return render_template('index.html', 
                             mobile_url=current_url,
                             localhost_url=current_url,
                             local_ip=current_url.split('//')[-1],
                             user=user,
                             user_roles=USER_ROLES)
                             
    except Exception as e:
        print(f"❌ 首页渲染错误: {str(e)}")
        # 使用简单的错误响应，避免模板错误循环
        return f"""
        <h1>首页加载失败</h1>
        <p>错误: {str(e)}</p>
        <a href="/login">重新登录</a>
        """, 500

@app.route('/query', methods=['GET', 'POST'])
@login_required()
def query_manufacturer():
    client = get_client()
    if not client:
        return render_template('error.html', error="数据库连接失败", message="请稍后重试")
    
    user = session.get('user')
    
    if request.method == 'POST':
        manufacturer_id = request.form.get('manufacturer_id', '').strip()
        
        if not manufacturer_id:
            return render_template('query.html', error='请输入厂家ID', user=user)
        
        try:
            if user['role'] == 'user' and user.get('manufacturer_id') != manufacturer_id:
                return render_template('query.html', 
                                     error='您只能查询自己厂家的信息', 
                                     user=user)
            
            manufacturer_response = client.select('manufacturers', {'manufacturer_id': f'eq.{manufacturer_id}'})
            
            if manufacturer_response['error']:
                return render_template('query.html', 
                                     error=f"查询失败: {manufacturer_response['error']}", 
                                     user=user)
            
            personnel_response = client.select('maintenance_personnel', {
                'manufacturer_id': f'eq.{manufacturer_id}',
                'is_active': 'eq.true'
            })
            
            personnel_data = personnel_response['data'] or []
            
            if manufacturer_response['data']:
                return render_template('manage.html', 
                                     manufacturer=manufacturer_response['data'][0],
                                     personnel=personnel_data,
                                     user=user)
            else:
                if user['role'] in ['super_admin', 'manufacturer_admin']:
                    return render_template('register.html', 
                                         manufacturer_id=manufacturer_id,
                                         user=user)
                else:
                    return render_template('query.html', 
                                         error='厂家不存在且您没有注册权限', 
                                         user=user)
                
        except Exception as e:
            print(f"查询错误: {e}")
            return render_template('query.html', error='系统错误，请稍后重试', user=user)
    
    return render_template('query.html', user=user)

# ========== 其余的路由保持不变 ==========

@app.route('/register', methods=['POST'])
@login_required(role=['super_admin', 'manufacturer_admin'])
def register_manufacturer():
    """新厂家注册"""
    try:
        data = {
            'manufacturer_id': request.form.get('manufacturer_id'),
            'name': request.form.get('name'),
            'contact_person': request.form.get('contact_person'),
            'phone': request.form.get('phone'),
            'email': request.form.get('email')
        }
        
        if not all([data['manufacturer_id'], data['name'], data['contact_person'], data['phone']]):
            return render_template('register.html', 
                                 manufacturer_id=data['manufacturer_id'],
                                 error='请填写所有必填字段',
                                 user=session.get('user'))
        
        response = client.insert('manufacturers', data)
        
        if response['error']:
            return render_template('register.html', 
                                 manufacturer_id=data['manufacturer_id'],
                                 error=f'注册失败: {response["error"]}',
                                 user=session.get('user'))
        else:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{data["manufacturer_id"]}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{data["manufacturer_id"]}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 user=session.get('user'))
            
    except Exception as e:
        print(f"注册错误: {e}")
        return render_template('register.html', 
                             manufacturer_id=request.form.get('manufacturer_id'),
                             error='系统错误，请稍后重试',
                             user=session.get('user'))

@app.route('/add_personnel', methods=['POST'])
@login_required()
def add_personnel():
    """新增保养人员"""
    try:
        manufacturer_id = request.form.get('manufacturer_id')
        user = session.get('user')
        
        if user['role'] == 'user' and user.get('manufacturer_id') != manufacturer_id:
            return render_template('error.html', 
                                error="权限不足", 
                                message="您只能管理自己厂家的人员"), 403
        
        manufacturer_name = request.form.get('manufacturer_name')
        
        new_personnel = {
            'manufacturer_id': manufacturer_id,
            'personnel_name': request.form.get('personnel_name'),
            'hire_date': request.form.get('hire_date'),
            'position': request.form.get('position'),
            'name_id': request.form.get('name_id'),
            'manufacturer_name': manufacturer_name,
            'note': request.form.get('note')
        }
        
        if not new_personnel['personnel_name']:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 error='请输入保养人员姓名',
                                 user=user)
        
        response = client.insert('maintenance_personnel', new_personnel)
        
        if response['error']:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 error=f'添加失败: {response["error"]}',
                                 user=user)
        else:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 success='保养人员添加成功',
                                 user=user)
        
    except Exception as e:
        print(f"添加人员错误: {e}")
        manufacturer_response = client.select(
            'manufacturers', 
            {'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}'}
        )
        
        personnel_response = client.select(
            'maintenance_personnel', 
            {
                'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}',
                'is_active': 'eq.true'
            }
        )
        
        personnel_data = personnel_response['data'] or []
        
        return render_template('manage.html', 
                             manufacturer=manufacturer_response['data'][0],
                             personnel=personnel_data,
                             error='添加失败，系统错误',
                             user=session.get('user'))

@app.route('/update_personnel', methods=['POST'])
@login_required()
def update_personnel():
    """更新保养人员信息"""
    try:
        update_data = {
            'personnel_name': request.form.get('personnel_name'),
            'hire_date': request.form.get('hire_date'),
            'position': request.form.get('position'),
            'name_id': request.form.get('name_id'),
            'manufacturer_name': request.form.get('manufacturer_name'),
            'note': request.form.get('note')
        }
        
        personnel_id = request.form.get('personnel_id')
        manufacturer_id = request.form.get('manufacturer_id')
        user = session.get('user')
        
        if user['role'] == 'user' and user.get('manufacturer_id') != manufacturer_id:
            return render_template('error.html', 
                                error="权限不足", 
                                message="您只能管理自己厂家的人员"), 403
        
        if not update_data['personnel_name']:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 error='请输入保养人员姓名',
                                 user=user)
        
        response = client.update(
            'maintenance_personnel', 
            update_data, 
            {'id': f'eq.{personnel_id}'}
        )
        
        if response['error']:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 error=f'更新失败: {response["error"]}',
                                 user=user)
        else:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 success='保养人员信息更新成功',
                                 user=user)
        
    except Exception as e:
        print(f"更新人员错误: {e}")
        manufacturer_response = client.select(
            'manufacturers', 
            {'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}'}
        )
        
        personnel_response = client.select(
            'maintenance_personnel', 
            {
                'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}',
                'is_active': 'eq.true'
            }
        )
        
        personnel_data = personnel_response['data'] or []
        
        return render_template('manage.html', 
                             manufacturer=manufacturer_response['data'][0],
                             personnel=personnel_data,
                             error='更新失败，系统错误',
                             user=session.get('user'))

@app.route('/delete_personnel', methods=['POST'])
@login_required()
def delete_personnel():
    """删除保养人员（软删除）"""
    try:
        personnel_id = request.form.get('personnel_id')
        manufacturer_id = request.form.get('manufacturer_id')
        user = session.get('user')
        
        if user['role'] == 'user' and user.get('manufacturer_id') != manufacturer_id:
            return render_template('error.html', 
                                error="权限不足", 
                                message="您只能管理自己厂家的人员"), 403
        
        response = client.update(
            'maintenance_personnel', 
            {
                'is_active': False
            }, 
            {'id': f'eq.{personnel_id}'}
        )
        
        if response['error']:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 error=f'删除失败: {response["error"]}',
                                 user=user)
        else:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 success='保养人员删除成功',
                                 user=user)
        
    except Exception as e:
        print(f"删除人员错误: {e}")
        manufacturer_response = client.select(
            'manufacturers', 
            {'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}'}
        )
        
        personnel_response = client.select(
            'maintenance_personnel', 
            {
                'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}',
                'is_active': 'eq.true'
            }
        )
        
        personnel_data = personnel_response['data'] or []
        
        return render_template('manage.html', 
                             manufacturer=manufacturer_response['data'][0],
                             personnel=personnel_data,
                             error='删除失败，系统错误',
                             user=session.get('user'))

@app.route('/restore_personnel', methods=['POST'])
@login_required()
def restore_personnel():
    """恢复已删除的保养人员"""
    try:
        personnel_id = request.form.get('personnel_id')
        manufacturer_id = request.form.get('manufacturer_id')
        user = session.get('user')
        
        if user['role'] == 'user' and user.get('manufacturer_id') != manufacturer_id:
            return render_template('error.html', 
                                error="权限不足", 
                                message="您只能管理自己厂家的人员"), 403
        
        response = client.update(
            'maintenance_personnel', 
            {
                'is_active': True
            }, 
            {'id': f'eq.{personnel_id}'}
        )
        
        if response['error']:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 error=f'恢复失败: {response["error"]}',
                                 user=user)
        else:
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
            personnel_data = personnel_response['data'] or []
            
            return render_template('manage.html', 
                                 manufacturer=manufacturer_response['data'][0],
                                 personnel=personnel_data,
                                 success='保养人员恢复成功',
                                 user=user)
        
    except Exception as e:
        print(f"恢复人员错误: {e}")
        manufacturer_response = client.select(
            'manufacturers', 
            {'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}'}
        )
        
        personnel_response = client.select(
            'maintenance_personnel', 
            {
                'manufacturer_id': f'eq.{request.form.get("manufacturer_id")}',
                'is_active': 'eq.true'
            }
        )
        
        personnel_data = personnel_response['data'] or []
        
        return render_template('manage.html', 
                             manufacturer=manufacturer_response['data'][0],
                             personnel=personnel_data,
                             error='恢复失败，系统错误',
                             user=session.get('user'))

@app.route('/user_management')
@login_required(role=['super_admin', 'manufacturer_admin'])
def user_management():
    """用户管理页面"""
    users_response = client.select('users')
    manufacturers_response = client.select('manufacturers')
    
    users = users_response['data']
    manufacturers = manufacturers_response['data']
    
    user = session.get('user')
    if user['role'] == 'manufacturer_admin':
        users = [u for u in users if u.get('manufacturer_id') == user.get('manufacturer_id')]
    
    return render_template('user_management.html', 
                         users=users, 
                         manufacturers=manufacturers,
                         user=user,
                         user_roles=USER_ROLES)

@app.route('/add_user', methods=['POST'])
@login_required(role=['super_admin', 'manufacturer_admin'])
def add_user():
    """添加新用户"""
    try:
        raw_password = request.form.get('password')
        
        user_data = {
            'username': request.form.get('username'),
            'password': hash_password(raw_password),
            'real_name': request.form.get('real_name'),
            'role': request.form.get('role'),
            'manufacturer_id': request.form.get('manufacturer_id') or None,
            'email': request.form.get('email'),
            'phone': request.form.get('phone'),
            'is_active': True,
            'created_by': session.get('user')['username']
        }
        
        if not all([user_data['username'], user_data['real_name'], user_data['role'], raw_password]):
            return jsonify({'success': False, 'error': '请填写所有必填字段'})
        
        current_user = session.get('user')
        if current_user['role'] == 'manufacturer_admin':
            if user_data['role'] != 'user':
                return jsonify({'success': False, 'error': '您只能创建普通用户'})
            user_data['manufacturer_id'] = current_user.get('manufacturer_id')
        
        existing_user_response = client.select('users', {'username': f'eq.{user_data["username"]}'})
        if existing_user_response['data']:
            return jsonify({'success': False, 'error': '用户名已存在'})
        
        response = client.insert('users', user_data)
        
        if response['error']:
            return jsonify({'success': False, 'error': response['error']})
        else:
            print(f"✅ 新用户 {user_data['username']} 创建成功")
            print(f"🔐 密码哈希: {user_data['password']}")
            return jsonify({'success': True, 'message': '用户添加成功'})
        
    except Exception as e:
        print(f"添加用户错误: {e}")
        return jsonify({'success': False, 'error': '系统错误'})

@app.route('/reset_password', methods=['POST'])
@login_required(role=['super_admin'])
def reset_password():
    """重置用户密码（仅超级管理员）"""
    try:
        username = request.form.get('username')
        new_password = request.form.get('new_password')
        
        if not username or not new_password:
            return jsonify({'success': False, 'error': '请提供用户名和新密码'})
        
        user_response = client.select('users', {'username': f'eq.{username}'})
        if not user_response['data']:
            return jsonify({'success': False, 'error': '用户不存在'})
        
        hashed_password = hash_password(new_password)
        update_response = client.update(
            'users', 
            {'password': hashed_password}, 
            {'username': f'eq.{username}'}
        )
        
        if update_response['error']:
            return jsonify({'success': False, 'error': update_response['error']})
        else:
            print(f"✅ 用户 {username} 密码重置成功")
            print(f"🔐 新密码哈希: {hashed_password}")
            return jsonify({'success': True, 'message': '密码重置成功'})
            
    except Exception as e:
        print(f"重置密码错误: {e}")
        return jsonify({'success': False, 'error': '系统错误'})
    
@app.route('/admin')
@login_required(role=['super_admin'])
def admin():
    """系统管理页面"""
    manufacturers_response = client.select('manufacturers')
    personnel_response = client.select('maintenance_personnel')
    users_response = client.select('users')
    
    data = {
        'manufacturers': manufacturers_response['data'],
        'maintenance_personnel': personnel_response['data'],
        'users': users_response['data']
    }
    
    return render_template('admin.html', data=data, user=session.get('user'))

@app.route('/export')
@login_required(role=['super_admin'])
def export_data():
    """导出数据"""
    manufacturers_response = client.select('manufacturers')
    personnel_response = client.select('maintenance_personnel')
    users_response = client.select('users')
    
    data = {
        'manufacturers': manufacturers_response['data'],
        'maintenance_personnel': personnel_response['data'],
        'users': users_response['data']
    }
    
    return jsonify(data)

@app.route('/check-structure')
#权限改为超级管理员
@login_required(role=['super_admin'])
def check_structure():
    """检查数据结构"""
    manufacturers_response = client.select('manufacturers', {'limit': '1'})
    personnel_response = client.select('maintenance_personnel', {'limit': '1'})
    
    manufacturers_data = manufacturers_response['data']
    personnel_data = personnel_response['data']
    
    manufacturers_ok = True
    manufacturers_fields = set()
    if manufacturers_data:
        manufacturers_fields = set(manufacturers_data[0].keys())
        expected_manufacturers_fields = {'id', 'manufacturer_id', 'name', 'contact_person', 'phone', 'email', 'created_at'}
        manufacturers_ok = manufacturers_fields == expected_manufacturers_fields
    
    personnel_ok = True
    personnel_fields = set()
    if personnel_data:
        personnel_fields = set(personnel_data[0].keys())
        expected_personnel_fields = {'id', 'manufacturer_id', 'personnel_name', 'hire_date', 'position', 'is_active', 'created_at', 'updated_at', 'name_id', 'manufacturer_name', 'note'}
        personnel_ok = personnel_fields == expected_personnel_fields
    
    return jsonify({
        'manufacturers_structure_ok': manufacturers_ok,
        'manufacturers_fields': list(manufacturers_fields),
        'personnel_structure_ok': personnel_ok,
        'personnel_fields': list(personnel_fields),
        'expected_manufacturers_fields': ['id', 'manufacturer_id', 'name', 'contact_person', 'phone', 'email', 'created_at'],
        'expected_personnel_fields': ['id', 'manufacturer_id', 'personnel_name', 'hire_date', 'position', 'is_active', 'created_at', 'updated_at', 'name_id', 'manufacturer_name', 'note']
    })

@app.route('/reset_admin')
def reset_admin():
    """重置管理员账户（开发使用）"""
    ensure_admin_user()
    return redirect(url_for('login'))

# 静态文件路由
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="页面未找到", message="您访问的页面不存在"), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理 - 使用简单HTML避免模板错误"""
    import traceback
    error_traceback = traceback.format_exc()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>500 - 服务器错误</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
            .error {{ background: #ffeaea; padding: 20px; border-radius: 5px; }}
            pre {{ background: #f5f5f5; padding: 15px; overflow: auto; font-size: 12px; }}
            .btn {{ display: inline-block; padding: 10px 15px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; margin: 5px; }}
        </style>
    </head>
    <body>
        <h1>🚨 500 - 服务器内部错误</h1>
        
        <div class="error">
            <h2>错误信息:</h2>
            <p><strong>{str(error)}</strong></p>
        </div>
        
        <div style="margin-top: 20px;">
            <h3>您可以尝试:</h3>
            <a href="/login" class="btn">🔄 重新登录</a>
            <a href="/index" class="btn">🏠 返回首页</a>
            <a href="/health" class="btn">❤️ 健康检查</a>
        </div>
        
        <div style="margin-top: 20px;">
            <details>
                <summary>查看技术详情（用于调试）</summary>
                <pre>{error_traceback}</pre>
            </details>
        </div>
    </body>
    </html>
    """, 500

# ========== 修正后的路由定义结束 ==========

# 启动配置
# if __name__ == '__main__':
#     port = int(os.environ.get('PORT', 10000))
#     print(f"🚀 启动厂家保养人员管理系统在端口 {port}")
#     app.run(host='0.0.0.0', port=port, debug=False)
# ========== 修改：主函数启动 ==========
if __name__ == '__main__':
    # 初始化应用
    if not init_app():
        logger.error("❌ 应用初始化失败，无法启动")
        exit(1)
    
    # 获取配置
    port = int(os.environ.get('PORT', 10000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # 启动信息
    startup_msg = f"""
    🚀 厂家保养人员管理系统启动
    📍 地址: {host}:{port}
    🔧 调试模式: {debug_mode}
    🛡️ 防休眠: 已启用 ({anti_sleep.platform} 优化)
    ⏰ 唤醒间隔: {anti_sleep.wakeup_interval}秒
    📊 健康检查: {request.host_url.rstrip('/')}/health
    🔔 唤醒端点: {request.host_url.rstrip('/')}/wakeup
    """
    
    print(startup_msg)
    logger.info(startup_msg)
    
    # 启动应用
    try:
        app.run(
            host=host,
            port=port,
            debug=debug_mode,
            threaded=True,  # 启用多线程
            use_reloader=False  # 生产环境禁用自动重载
        )
    except KeyboardInterrupt:
        logger.info("👋 应用被用户中断")
    except Exception as e:
        logger.error(f"❌ 应用启动失败: {e}")