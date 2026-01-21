"""App - Flask应用工厂"""
from flask import Flask, jsonify

from core.config import REMOTE_SERVER_PORT
from utils.logger import get_logger

from .routes import api_bp

logger = get_logger("remote_server_app")


def create_app():
    """创建Flask应用实例"""
    app = Flask(__name__)
    
    # 注册蓝图
    app.register_blueprint(api_bp)
    
    # 注册根路由
    @app.route('/')
    def index():
        return jsonify({
            "service": "ailabber Remote Server",
            "version": "2.0.0",
            "description": "远程 Slurm 作业管理服务",
            "api_prefix": "/api"
        })
    
    logger.info("Flask应用创建完成")
    return app


def run_app():
    """运行Flask应用"""
    app = create_app()
    
    logger.info(f"Remote Server 启动于端口 {REMOTE_SERVER_PORT}")
    
    app.run(
        host='0.0.0.0',
        port=REMOTE_SERVER_PORT,
        debug=False,
        threaded=True
    )

run_app()