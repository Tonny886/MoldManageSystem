# 新增 fast_recovery.py
import sys
import os
sys.path.append(os.path.dirname(__file__))

def quick_start():
    """快速启动函数，用于冷启动优化"""
    from app import app, init_app
    
    # 最小化初始化
    init_app()
    
    # 快速响应测试
    @app.route('/quick')
    def quick():
        return "🚀 Quick Response OK", 200
    
    return app