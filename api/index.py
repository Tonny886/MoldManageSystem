import sys
import os
from flask import Flask

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

# 设置环境变量（如果还没有设置）
os.environ.setdefault('FLASK_ENV', 'production')

def create_app():
    """创建 Flask 应用"""
    try:
        # 延迟导入以避免循环导入
        from app import app as flask_app
        print("✅ 成功导入 Flask 应用")
        return flask_app
    except Exception as e:
        print(f"❌ 导入 Flask 应用失败: {e}")
        # 创建备用应用
        fallback_app = Flask(__name__)
        
        @fallback_app.route('/')
        def index():
            return "Flask 应用加载成功，但可能存在配置问题"
            
        @fallback_app.route('/health')
        def health():
            return "OK"
            
        @fallback_app.route('/<path:path>')
        def catch_all(path):
            return f"路由 {path} 未正确配置"
            
        return fallback_app

# 创建应用实例
app = create_app()

# Vercel 需要这个
if __name__ == '__main__':
    app.run(debug=False)