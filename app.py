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
# 修复 Vercel 会话配置
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800  # 30分钟
)

# Supabase 配置
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# 用户角色定义
USER_ROLES = {
    'super_admin': '超级管理员',
    'manufacturer_admin': '厂家管理员', 
    'user': '普通用户'
}

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
    # 使用简单的SHA256哈希，不加盐以便调试
    return hashlib.sha256(password.encode()).hexdigest()

class SupabaseClient:
    """Supabase 数据客户端"""
    def __init__(self):
        try:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase 客户端已初始化")
        except Exception as e:
            print(f"❌ Supabase 初始化失败: {e}")
            raise
    
    def select(self, table, filters=None):
        """查询数据"""
        try:
            # 构建基础查询
            query = self.client.table(table).select("*")
            
            # 应用过滤器
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
            
            # 执行查询
            response = query.execute()
            
            # 处理 limit（在内存中处理，因为 Supabase 的 limit 用法不同）
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
            # 添加时间戳
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
            # 构建基础查询
            query = self.client.table(table)
            
            # 应用过滤器
            if filters:
                for key, value in filters.items():
                    if key == 'id' and value.startswith('eq.'):
                        item_id = int(value[3:])
                        query = query.eq('id', item_id)
                    elif key == 'manufacturer_id' and value.startswith('eq.'):
                        manufacturer_id = value[3:]
                        query = query.eq('manufacturer_id', manufacturer_id)
            
            # 更新时间戳
            if table == 'maintenance_personnel':
                data['updated_at'] = datetime.now().isoformat()
            
            # 执行更新
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
        client = SupabaseClient()
        
        # 检查是否已存在管理员用户
        user_response = client.select('users', {
            'username': 'eq.admin'
        })
        
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
            else:
                print("✅ 管理员用户创建成功")
                print(f"📝 用户名: admin")
                print(f"🔐 密码: admin123")
                print(f"🗝️ 密码哈希: {admin_user['password']}")
        else:
            print("✅ 管理员用户已存在")
            
    except Exception as e:
        print(f"❌ 确保管理员用户存在时出错: {e}")

def init_supabase_data():
    """初始化 Supabase 数据"""
    try:
        client = SupabaseClient()
        
        # 检查是否已有厂家数据
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
            
            client.insert('manufacturers', example_manufacturer)
            print("✅ 示例厂家创建成功")
        
        # 确保管理员用户存在
        ensure_admin_user()
        
    except Exception as e:
        print(f"❌ 初始化 Supabase 数据失败: {e}")

# 初始化 Supabase 客户端
print("🚀 启动厂家保养人员管理系统...")
print("📊 使用 Supabase 云数据库")
try:
    client = SupabaseClient()
    # 初始化数据
    init_supabase_data()
except Exception as e:
    print(f"❌ 系统启动失败: {e}")
    client = None

def login_required(role=None):
    """登录验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            
            if role and session['user']['role'] not in role:
                return render_template('error.html', 
                    error="权限不足", 
                    message="您没有访问此页面的权限"), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

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
            # 查询用户信息
            user_response = client.select('users', {
                'username': f'eq.{username}'
            })
            
            print(f"🔐 登录尝试: 用户名={username}")
            print(f"🔍 找到 {len(user_response['data'])} 个匹配用户")
            
            # 检查用户是否存在
            if not user_response['data']:
                print(f"❌ 用户不存在: {username}")
                return render_template('login.html', error='用户名或密码错误')
            
            user = user_response['data'][0]
            
            # 检查用户是否激活
            if not user.get('is_active', True):
                print(f"❌ 用户已被禁用: {username}")
                return render_template('login.html', error='用户已被禁用，请联系管理员')
            
            # 验证密码
            input_password_hash = hash_password(password)
            stored_password_hash = user['password']
            
            print(f"🔑 密码验证:")
            print(f"   输入密码: {password}")
            print(f"   输入哈希: {input_password_hash}")
            print(f"   存储哈希: {stored_password_hash}")
            print(f"   匹配结果: {'成功' if stored_password_hash == input_password_hash else '失败'}")
            
            if stored_password_hash != input_password_hash:
                print(f"❌ 密码错误: {username}")
                return render_template('login.html', error='用户名或密码错误')
            
            # 登录成功
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'real_name': user['real_name'],
                'role': user['role'],
                'manufacturer_id': user.get('manufacturer_id')
            }
            
            print(f"✅ 用户 {username} 登录成功，角色: {user['role']}")
            return redirect(url_for('index'))
                
        except Exception as e:
            print(f"❌ 登录错误: {e}")
            import traceback
            traceback.print_exc()
            return render_template('login.html', error='系统错误，请稍后重试')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """用户退出登录"""
    username = session.get('user', {}).get('username', '未知用户')
    session.pop('user', None)
    print(f"✅ 用户 {username} 已退出登录")
    return redirect(url_for('login'))
# 确保静态文件路由
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

@app.route('/')
@login_required()
def index():
    """系统首页"""
    local_ip = get_local_ip()
    port = 5000
    
    mobile_url = f"http://{local_ip}:{port}"
    qr_code_data = generate_qr_code(mobile_url)
    localhost_url = f"http://localhost:{port}"
    
    return render_template('index.html', 
                         qr_code_data=qr_code_data, 
                         mobile_url=mobile_url,
                         localhost_url=localhost_url,
                         local_ip=local_ip,
                         user=session.get('user'),
                         user_roles=USER_ROLES)

@app.route('/query', methods=['GET', 'POST'])
@login_required()
def query_manufacturer():
    """查询厂家信息页面"""
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
            
            manufacturer_response = client.select(
                'manufacturers', 
                {'manufacturer_id': f'eq.{manufacturer_id}'}
            )
            
            if manufacturer_response['error']:
                return render_template('query.html', 
                                     error=f"查询失败: {manufacturer_response['error']}", 
                                     user=user)
            
            personnel_response = client.select(
                'maintenance_personnel', 
                {
                    'manufacturer_id': f'eq.{manufacturer_id}',
                    'is_active': 'eq.true'
                }
            )
            
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
        # 获取原始密码
        raw_password = request.form.get('password')
        
        user_data = {
            'username': request.form.get('username'),
            'password': hash_password(raw_password),  # 确保密码哈希
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
        
        # 查找用户
        user_response = client.select('users', {'username': f'eq.{username}'})
        if not user_response['data']:
            return jsonify({'success': False, 'error': '用户不存在'})
        
        # 更新密码为哈希值
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
    # 获取所有数据用于统计
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
@login_required(role=['super_admin', 'manufacturer_admin'])
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
@login_required(role=['super_admin', 'manufacturer_admin'])
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
    # 确保管理员用户存在
    ensure_admin_user()
    return redirect(url_for('login'))

@app.route('/debug')
def debug():
    """调试信息页面"""
    info = {
        "app_running": True,
        "database_connected": client is not None,
        "session_user": session.get('user'),
        "environment": "production",
        "supabase_url_set": bool(os.getenv('SUPABASE_URL')),
        "supabase_key_set": bool(os.getenv('SUPABASE_KEY'))
    }
    return jsonify(info)

@app.route('/fix-login')
def fix_login():
    """修复登录会话"""
    session.clear()
    return redirect(url_for('login'))
@app.route('/test-db')
def test_db():
    """测试数据库连接"""
    try:
        # 测试查询
        test_response = client.select('users', {'limit': '1'})
        
        if test_response['error']:
            return jsonify({
                "database_status": "error",
                "error": test_response['error']
            })
        else:
            return jsonify({
                "database_status": "connected",
                "user_count": len(test_response['data'])
            })
    except Exception as e:
        return jsonify({
            "database_status": "failed",
            "error": str(e)
        })
@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return render_template('error.html', 
                         error="页面未找到", 
                         message="您访问的页面不存在"), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    return render_template('error.html', 
                         error="服务器内部错误", 
                         message="服务器遇到意外错误，请稍后重试"), 500

def fix_existing_passwords():
    """修复现有用户的明文密码"""
    try:
        client = SupabaseClient()
        
        # 获取所有用户
        users_response = client.select('users')
        if users_response['error']:
            print(f"❌ 获取用户列表失败: {users_response['error']}")
            return
        
        for user in users_response['data']:
            current_password = user['password']
            
            # 检查密码是否是明文（不是64字符的哈希）
            if len(current_password) != 64:
                print(f"🔄 修复用户 {user['username']} 的密码...")
                
                # 假设当前密码就是正确的明文密码
                hashed_password = hash_password(current_password)
                
                # 更新密码
                update_response = client.update(
                    'users',
                    {'password': hashed_password},
                    {'id': f'eq.{user["id"]}'}
                )
                
                if update_response['error']:
                    print(f"❌ 修复用户 {user['username']} 密码失败: {update_response['error']}")
                else:
                    print(f"✅ 用户 {user['username']} 密码修复成功")
        
        print("🎉 所有用户密码修复完成")
        
    except Exception as e:
        print(f"❌ 修复密码时出错: {e}")
  # 在需要时运行这个函数
  # fix_existing_passwords()

if __name__ == '__main__':
    # 这个块在 Vercel 上不会执行
    app.run(debug=True)
   
# if __name__ == '__main__':
#     local_ip = get_local_ip()
#     port = 5000
#     print("=" * 60)
#     print("厂家保养人员管理系统 - 权限管理版")
#     print("=" * 60)
#     print("✅ 使用 Supabase 云数据库")
#     print("👥 用户权限管理系统已启用")
#     print("🔐 默认管理员账号: admin / admin123")
#     print("📱 手机访问: http://{}:{}".format(local_ip, port))
#     print("🌐 本机访问: http://localhost:{}".format(port))
#     print("👑 超级管理员: 全系统权限")
#     print("🏭 厂家管理员: 管理指定厂家和用户")
#     print("👤 普通用户: 仅查看和管理自己厂家的信息")
#     print("=" * 60)
#     print("💡 如果登录有问题，请访问: http://localhost:5000/reset_admin")
#     print("📱 使用手机扫描首页二维码即可访问系统")
#     print("=" * 60)
    
#     app.run(debug=True, host='0.0.0.0', port=port)