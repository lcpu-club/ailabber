"""配置常量"""
from logging import DEBUG, INFO
from pathlib import Path

# ============ 服务端口 ============
LOCAL_PROXY_PORT = 8080
REMOTE_SERVER_PORT = 8080

# ============ 日志配置 ============
LOG_LEVEL_CONSOLE = INFO
LOG_LEVEL_FILE = DEBUG

# ============ URL配置 ============
LOCAL_PROXY_URL = f"http://127.0.0.1:{LOCAL_PROXY_PORT}"
SSH_PRIVATE_KEY = Path.home() / ".ssh" / "id_rsa"  # SSH 私钥路径

# ============ local->remote服务器配置 ============
REMOTE_SSH_HOST = "1.1.1.1"          # 远程服务器地址
REMOTE_SSH_PORT = 22                 # SSH 端口
REMOTE_SSH_USER = "root"             # SSH 用户名
REMOTE_BASE_DIR = "/root"            # 远程服务器用户目录基础路径
REMOTE_SERVER_URL = f"http://127.0.0.1:{REMOTE_SERVER_PORT}"  # 远程服务器API地址（通过SSH隧道）

# ============ 本地路径 ============
DATA_DIR = Path.home() / ".ailabber"
LOCAL_DB_PATH = DATA_DIR / "local_proxy.db"
LOCAL_TMP_DIR = DATA_DIR / "tmp"     # 本地临时目录（用于rsync前的暂存）

# ============ 轮询间隔 (秒) ============
POLL_INTERVAL = 5


# ============ 初始化 ============
def ensure_dirs():
    """确保所有必要目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_TMP_DIR.mkdir(parents=True, exist_ok=True)


# 导入时自动创建目录
ensure_dirs()
