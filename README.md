# ailabber - 分布式 Slurm 任务调度系统

ailabber 是一个轻量级的分布式任务调度系统，支持本地和远程 Slurm 集群任务提交。

## 架构概述

```
┌─────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   CLI       │ ───► │  Local Proxy    │ ───► │  Remote Server  │
│  (客户端)    │      │  (本地代理)      │      │  (远程服务器)    │
└─────────────┘      └─────────────────┘      └─────────────────┘
                            │                         │
                            ▼                         ▼
                     ┌─────────────┐          ┌─────────────┐
                     │ Local Slurm │          │ Remote Slurm│
                     │  (本地集群)  │          │  (远程集群)  │
                     └─────────────┘          └─────────────┘
```

### 组件说明

1. **CLI (client/cli.py)**: 命令行客户端，用户交互入口
2. **Local Proxy (server/local_proxy.py)**: 本地代理服务器
   - 接收 CLI 请求
   - 本地任务：直接提交到本地 Slurm
   - 远程任务：rsync 文件后调用远程 API
   - 后台轮询任务状态
3. **Remote Server (server/remote_server.py)**: 远程服务器（极简设计）
   - 接收任务提交请求 → 生成 Slurm 脚本并提交
   - 接受状态轮询 → 返回 Slurm 作业状态
   - 返回日志和结果文件

## 安装

```bash
# 安装依赖
pip install flask sqlalchemy shortuuid requests

# 或使用 uv
uv sync
```

## 快速开始

### 1. 启动本地代理

```bash
python -m server.local_proxy
# 或
ailabber-proxy
```

### 2. (可选) 启动远程服务器

在远程 Slurm 集群上运行：

```bash
python -m server.remote_server
# 或
ailabber-remote
```

### 3. 提交任务

```bash
# 提交到本地 Slurm
ailabber submit local ./task_config.toml

# 提交到远程 Slurm
ailabber submit remote ./task_config.toml
```

## 配置文件

### task_config.toml

```toml
[resources]
gpus = 1
cpus = 4
memory = "32G"
time_limit = "4:00:00"    # Slurm 时间限制

[environment]
pyproject_toml = "./pyproject.toml"
uv_lock = "./uv.lock"
extra_wheels = []

[submit]
upload = "."              # 要同步的目录
ignore = [                # 忽略的文件/目录
    "./__pycache__/",
    "./.git/",
    "./.venv/"
]

[run]
workdir = "."             # 工作目录
commands = [              # 执行命令
    "python train.py --config configs/resnet50.yaml"
]

[fetch]
logs = ["./logs"]         # 日志目录
results = ["./output"]    # 结果目录
```

### shared/config.py 配置

```python
# 服务端口
LOCAL_PROXY_PORT = 8080
REMOTE_SERVER_PORT = 8080

# 远程服务器 SSH 配置
REMOTE_SSH_HOST = "your-server.com"
REMOTE_SSH_PORT = 22
REMOTE_SSH_USER = "username"
REMOTE_BASE_DIR = "/home/username"

# 轮询间隔
POLL_INTERVAL = 5  # 秒
```

## CLI 命令

```bash
ailabber help                    # 显示帮助
ailabber whoami                  # 查看当前用户
ailabber submit [local|remote] [config]  # 提交任务
ailabber status <task_id>        # 查看任务状态
ailabber list [status]           # 列出任务
ailabber fetch <task_id> [dir]   # 下载结果
ailabber cancel <task_id>        # 取消任务
```

## API 端点

### Local Proxy (localhost:8080)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | /api/submit | 提交任务 |
| GET | /api/status/<task_id> | 获取任务状态 |
| GET | /api/tasks | 列出用户任务 |
| GET | /api/logs/<task_id> | 获取任务日志 |
| GET | /api/fetch/<task_id> | 下载任务结果 |
| POST | /api/cancel/<task_id> | 取消任务 |
| GET | /health | 健康检查 |

### Remote Server (远程:8080)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | /api/submit | 提交 Slurm 作业 |
| GET | /api/status/<slurm_job_id> | 查询作业状态 |
| GET | /api/logs/<task_id> | 获取日志 |
| GET | /api/fetch/<task_id> | 下载结果 |
| POST | /api/cancel/<slurm_job_id> | 取消作业 |
| GET | /health | 健康检查 |

## 任务状态

| 状态 | 说明 |
|------|------|
| pending | 等待中 |
| running | 运行中 |
| completed | 已完成 |
| failed | 失败 |
| canceled | 已取消 |

## 目录结构

```
ailabber/
├── client/
│   ├── __init__.py
│   └── cli.py              # 命令行客户端
├── server/
│   ├── __init__.py
│   ├── local_proxy.py      # 本地代理服务器
│   └── remote_server.py    # 远程服务器
├── shared/
│   ├── __init__.py
│   ├── config.py           # 配置常量
│   ├── database.py         # 数据库模型
│   ├── logger.py           # 日志工具
│   └── slurm.py            # Slurm 工具函数
├── utils/
│   ├── __init__.py
│   └── db_init.py          # 数据库初始化
├── pyproject.toml
├── task_config.toml        # 示例任务配置
└── README.md
```

## 工作流程

### 本地任务

1. CLI 发送任务到 Local Proxy
2. Local Proxy 生成 Slurm 脚本
3. 提交到本地 Slurm 集群
4. 后台轮询状态更新

### 远程任务

1. CLI 发送任务到 Local Proxy
2. Local Proxy rsync 文件到远程服务器
3. 调用 Remote Server API 提交 Slurm 作业
4. Remote Server 生成并提交 Slurm 脚本
5. Local Proxy 轮询远程状态

## 注意事项

1. 确保本地和远程都安装了 Slurm
2. 远程任务需要配置 SSH 密钥免密登录
3. 确保 rsync 命令可用
4. 远程服务器需要开放对应端口或配置 SSH 隧道

## License

MIT