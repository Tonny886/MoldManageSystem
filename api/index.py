import sys
import os

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# 导入 Flask 应用
from app import app

# Vercel 需要这个变量名为 app
# 不需要重命名，直接使用导入的 app