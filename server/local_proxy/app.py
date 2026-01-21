"""App - Flask应用工厂"""
from flask import Flask, jsonify

from core.database import init_local_db
from core.config import LOCAL_PROXY_PORT
from utils.logger import get_logger

from .routes import api_bp
from .services import get_polling_service

logger = get_logger("local_proxy_app")


def create_app():
    """创建Flask应用实例"""
    app = Flask(__name__)
    
    # 初始化数据库
    init_local_db()
    logger.info("数据库初始化完成")
    
    # 注册蓝图
    app.register_blueprint(api_bp)
    
    # 注册根路由
    @app.route('/')
    def index():
        return jsonify({
            "service": "ailabber Local Proxy",
            "version": "2.0.0",
            "description": "本地代理服务器 - 支持本地/远程 Slurm 调度",
            "api_prefix": "/api"
        })
    
    logger.info("Flask应用创建完成")
    return app


def run_app():
    """运行Flask应用"""
    # 创建应用
    app = create_app()
    
    # 启动轮询服务
    polling_service = get_polling_service()
    polling_service.start()
    logger.info("任务轮询服务已启动")
    
    # 运行Flask应用
    logger.info(f"Local Proxy 服务器启动于端口 {LOCAL_PROXY_PORT}")
    
    try:
        app.run(
            host='127.0.0.1',
            port=LOCAL_PROXY_PORT,
            debug=False,
            threaded=True
        )
    finally:
        # 停止轮询服务
        polling_service.stop()
        logger.info("服务器已停止")

run_app()