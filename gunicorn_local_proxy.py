"""
Gunicorn配置文件 - Local Proxy 本地代理服务器
运行命令: gunicorn -c gunicorn_local_proxy.py "server.local_proxy.app:create_app()"
"""
from pathlib import Path

# ============ 服务器套接字 ============
# 绑定地址和端口
bind = "127.0.0.1:8080"

# 挂起连接的最大数量
backlog = 2048


# ============ 工作进程 ============
# 工作进程数
workers = 8

# 使用 gthread 支持多线程处理
worker_class = "gthread"

# 每个worker的线程数
threads = 2

# 工作进程的最大请求数，超过后重启该worker（防止内存泄漏）
max_requests = 1000
max_requests_jitter = 50  # 添加随机抖动避免所有worker同时重启


# ============ 超时设置 ============
# Worker超时时间（秒）
timeout = 120

# Worker优雅重启的超时时间
graceful_timeout = 30

# Keep-Alive连接保持时间（秒）
keepalive = 5


# ============ 日志配置 ============
# 日志目录
log_dir = Path.home() / ".ailabber" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

# 访问日志文件
accesslog = str(log_dir / "local_proxy_access.log")

# 错误日志文件
errorlog = str(log_dir / "local_proxy_error.log")

# 日志级别: debug, info, warning, error, critical
loglevel = "info"

# 访问日志格式
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'


# ============ 进程命名 ============
# 进程名称前缀
proc_name = "ailabber_local_proxy"


# ============ Server Mechanics ============
# 是否以守护进程方式运行
daemon = False

# PID文件路径
pidfile = str(Path.home() / ".ailabber" / "local_proxy.pid")

# 临时目录
tmp_upload_dir = str(Path.home() / ".ailabber" / "tmp")


# ============ 应用预加载 ============
# 在worker fork之前加载应用代码（提升性能，但某些场景可能有问题）
preload_app = False  # 设为False因为需要在每个worker中启动轮询服务


# ============ 用户和组 ============
# user = "nobody"
# group = "nogroup"


# ============ 服务器钩子函数 ============
def on_starting(server):
    """服务器启动时调用"""
    print("=" * 60)
    print(" Local Proxy Server 正在启动...")
    print(f"绑定地址: {bind}")
    print(f"工作进程数: {workers}")
    print(f"线程数: {threads}")
    print("=" * 60)


def when_ready(server):
    """服务器准备就绪时调用"""
    print(" Local Proxy Server 已就绪，可以接受连接")


def on_exit(server):
    """服务器退出时调用"""
    print(" Local Proxy Server 已停止")


def pre_fork(server, worker):
    """Worker fork之前调用"""
    pass


def post_fork(server, worker):
    """Worker fork之后调用"""
    server.log.info(f"Worker {worker.pid} 已启动")


def pre_exec(server):
    """在重新执行master进程之前调用"""
    server.log.info("Master进程正在重新执行")


def worker_int(worker):
    """Worker收到SIGINT或SIGQUIT信号时调用"""
    worker.log.info(f"Worker {worker.pid} 收到终止信号")


def worker_abort(worker):
    """Worker被超时杀死时调用"""
    worker.log.warning(f"Worker {worker.pid} 因超时被终止")
