"""配置常量"""
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from pathlib import Path

# ============ 服务端口 ============
LOCAL_PROXY_PORT = 8080
LOCAL_FRPC_PORT = 7000
REMOTE_SERVER_PORT = 8080
REMOTE_FRPS_PORT = 7000

# ============ 日志配置 ============
LOG_LEVEL_CONSOLE = INFO
LOG_LEVEL_FILE = DEBUG

# ============ URL配置 ============
LOCAL_PROXY_URL = f"http://127.0.0.1:{LOCAL_PROXY_PORT}"

# ============ path ============
DATA_DIR = Path.home() / ".ailabber"
LOCAL_DB_PATH = DATA_DIR / "local_proxy.db"
REMOTE_DB_PATH = DATA_DIR / "remote_server.db"

# ============ 轮询间隔 (秒) ============
POLL_INTERVAL = 5

# ============ 确保目录存在 ============
def ensure_dirs():
    """确保所有必要目录存在"""
    for path in [DATA_DIR]:
        path.mkdir(parents=True, exist_ok=True)

# 导入时自动创建目录
ensure_dirs()