import os
from dotenv import load_dotenv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, send_from_directory, url_for, session
import json
import qrcode
import base64
from io import BytesIO
import socket
import hashlib
from functools import wraps
from supabase import create_client, Client

# 加载环境变量
load_dotenv()

# 创建 Flask 应用
app = Flask(__name__,
    static_folder='static',
    static_url_path='/static',
    template_folder='templates'
)
app.secret_key = os.getenv('SECRET_KEY', 'manufacturer-system-secret-key-2024')

# 修复 Railway 会话配置
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800  # 30分钟
)

# Supabase 配置 - 使用延迟初始化
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# 用户角色定义
USER_ROLES = {
    'super_admin': '超级管理员',
    'manufacturer_admin': '厂家管理员', 
    'user': '普通用户'
}

# 全局客户端变量 - 延迟初始化
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

def init_app():
    """应用初始化（在第一个请求时调用）"""
    try:
        client = get_client()
        if client:
            init_supabase_data()
            print("🚀 厂家保养人员管理系统初始化完成")
    except Exception as e:
        print(f"❌ 应用初始化失败: {e}")

# 上下文处理器 - 自动在所有模板中注入 user_roles
@app.context_processor
def inject_user_roles():
    """自动在所有模板中注入 user_roles 变量"""
    return dict(user_roles=USER_ROLES)

def get_local_ip():
    """获取本机在局域网中的IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"获取本机IP失败: {e}")
        return "127.0.0.1"

def generate_qr_code(url):
    """生成二维码图片并返回base64编码"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        img_str = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"二维码生成失败: {e}")
        return None

def hash_password(password):
    """密码加密"""
    return hashlib.sha256(password.encode()).hexdigest()

class SupabaseClient:
    """Supabase 数据客户端"""
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise Exception("Supabase 环境变量未设置")
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    def select(self, table, filters=None):
        """查询数据"""
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
        """插入数据"""
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
        """更新数据"""
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
    """确保管理员用户存在"""
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
    """初始化 Supabase 数据"""
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
        
        # 确保管理员用户存在
        return ensure_admin_user()
        
    except Exception as e:
        print(f"❌ 初始化 Supabase 数据失败: {e}")
        return False

def login_required(role=None):
    """登录验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 延迟初始化应用
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
    """在每次请求前检查初始化"""
    if client is None:
        init_app()

@app.route('/')
def home():
    """首页 - 用于健康检查"""
    return jsonify({
        "status": "success", 
        "message": "厂家保养人员管理系统",
        "platform": "Railway",
        "database_connected": client is not None
    })

@app.route('/health')
def health():
    """健康检查端点"""
    db_status = "connected" if client else "disconnected"
    return jsonify({
        "status": "healthy",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录页面"""
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
            
            # 查询用户信息
            user_response = client.select('users', {'username': f'eq.{username}'})
            
            if not user_response['data']:
                return render_template('login.html', error='用户名或密码错误')
            
            user = user_response['data'][0]
            
            # 检查用户是否激活
            if not user.get('is_active', True):
                return render_template('login.html', error='用户已被禁用，请联系管理员')
            
            # 验证密码
            input_password_hash = hash_password(password)
            stored_password_hash = user['password']
            
            if stored_password_hash != input_password_hash:
                return render_template('login.html', error='用户名或密码错误')
            
            # 登录成功
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
        # 在 Railway 环境中，使用动态URL生成二维码
        current_url = request.host_url.rstrip('/')
        qr_code_data = generate_qr_code(current_url)
        
        return render_template('index.html', 
                             qr_code_data=qr_code_data, 
                             mobile_url=current_url,
                             localhost_url=current_url,
                             local_ip=current_url.split('//')[-1],
                             user=session.get('user'),
                             user_roles=USER_ROLES)
    except Exception as e:
        print(f"首页错误: {e}")
        return render_template('index.html', 
                             user=session.get('user'),
                             user_roles=USER_ROLES)

# 其他路由函数保持不变，但需要在每个函数开头添加客户端检查
@app.route('/query', methods=['GET', 'POST'])
@login_required()
def query_manufacturer():
    """查询厂家信息页面"""
    client = get_client()
    if not client:
        return render_template('error.html', error="数据库连接失败", message="请稍后重试")
    
    user = session.get('user')
    
    if request.method == 'POST':
        manufacturer_id = request.form.get('manufacturer_id', '').strip()
        
        if not manufacturer_id:
            return render_template('query.html', error='请输入厂家ID', user=user)
        
        try:
            # 权限检查
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
    return render_template('error.html', error="服务器内部错误", message="服务器遇到意外错误，请稍后重试"), 500

# Railway 需要的启动配置
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 启动厂家保养人员管理系统在端口 {port}")
    app.run(host='0.0.0.0', port=port, debug=False)