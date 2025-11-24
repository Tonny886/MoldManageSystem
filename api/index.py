import sys
import os
import traceback
import logging
from flask import Flask, jsonify, request

# 配置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

print("🚀 Vercel Flask 应用启动中...")
print(f"📁 工作目录: {os.getcwd()}")
print(f"📁 文件位置: {__file__}")

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

print(f"📁 项目根目录: {project_root}")
print(f"🐍 Python 路径: {sys.path}")

def debug_environment():
    """调试环境信息"""
    env_info = {
        "python_version": sys.version,
        "current_directory": os.getcwd(),
        "project_root": project_root,
        "files_in_root": os.listdir('.') if os.path.exists('.') else "N/A",
        "files_in_project": os.listdir(project_root) if os.path.exists(project_root) else "N/A",
        "environment_variables": {
            "SECRET_KEY": bool(os.getenv('SECRET_KEY')),
            "SUPABASE_URL": bool(os.getenv('SUPABASE_URL')),
            "SUPABASE_KEY": bool(os.getenv('SUPABASE_KEY')),
            "PYTHONPATH": os.getenv('PYTHONPATH')
        }
    }
    
    print("🔍 环境调试信息:")
    for key, value in env_info.items():
        print(f"   {key}: {value}")
    
    return env_info

# 先调试环境
debug_environment()

try:
    print("🔄 正在导入 Flask 应用...")
    
    # 检查关键文件
    critical_files = {
        'app.py': os.path.join(project_root, 'app.py'),
        'requirements.txt': os.path.join(project_root, 'requirements.txt'),
        'static/style.css': os.path.join(project_root, 'static', 'style.css'),
        'templates/base.html': os.path.join(project_root, 'templates', 'base.html'),
        'templates/login.html': os.path.join(project_root, 'templates', 'login.html')
    }
    
    print("📁 文件检查:")
    for name, path in critical_files.items():
        exists = os.path.exists(path)
        print(f"   {'✅' if exists else '❌'} {name}: {exists}")
        if not exists and os.path.exists(os.path.dirname(path)):
            print(f"     目录内容: {os.listdir(os.path.dirname(path))}")
    
    # 导入应用
    from app import app as flask_app
    print("✅ Flask 应用导入成功!")
    
    # 创建应用实例
    app = flask_app
    
except Exception as e:
    print(f"💥 应用创建失败: {e}")
    print("🔍 详细错误堆栈:")
    traceback.print_exc()
    
    # 创建详细的错误报告应用
    from flask import Flask, render_template_string
    
    app = Flask(__name__)
    
    ERROR_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>应用启动错误</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .error { background: #ffeaea; padding: 20px; border-radius: 5px; }
            .success { background: #eaffea; padding: 20px; border-radius: 5px; }
            pre { background: #f5f5f5; padding: 15px; overflow: auto; }
        </style>
    </head>
    <body>
        <h1>🚨 Flask 应用启动失败</h1>
        
        <div class="error">
            <h2>错误信息:</h2>
            <pre>{{ error }}</pre>
        </div>
        
        <div class="success">
            <h2>环境信息:</h2>
            <pre>{{ env_info }}</pre>
        </div>
        
        <div>
            <h2>文件结构:</h2>
            <pre>{{ file_structure }}</pre>
        </div>
        
        <p><a href="/health">健康检查</a> | <a href="/debug">调试信息</a></p>
    </body>
    </html>
    """
    
    @app.route('/')
    def error_page():
        import traceback
        error_details = traceback.format_exc()
        
        # 获取文件结构
        file_structure = {}
        if os.path.exists(project_root):
            for root, dirs, files in os.walk(project_root):
                level = root.replace(project_root, '').count(os.sep)
                indent = ' ' * 2 * level
                file_structure[f"{indent}{os.path.basename(root)}/"] = []
                sub_indent = ' ' * 2 * (level + 1)
                for file in files:
                    file_structure[f"{indent}{os.path.basename(root)}/"].append(f"{sub_indent}{file}")
        
        return render_template_string(
            ERROR_TEMPLATE,
            error=error_details,
            env_info=debug_environment(),
            file_structure=file_structure
        )
    
    @app.route('/health')
    def health():
        return "OK"
    
    @app.route('/debug')
    def debug():
        return jsonify(debug_environment())

# 添加全局错误处理
@app.errorhandler(500)
def handle_500(error):
    import traceback
    error_traceback = traceback.format_exc()
    
    error_html = f"""
    <html>
    <body>
        <h1>500 服务器内部错误</h1>
        <pre>{error_traceback}</pre>
        <p>请求路径: {request.path}</p>
        <p><a href="/">返回首页</a></p>
    </body>
    </html>
    """
    return error_html, 500

# Vercel 需要这个
application = app

print("🎉 应用初始化完成，准备处理请求")