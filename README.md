# ailabber - 分布式 Slurm 任务调度系统

ailabber 是一个轻量级的分布式任务调度系统，支持本地和远程 Slurm 集群任务提交。

## 核心功能

1. **通过代理提交远程任务**: `ailabber submit remote <config.toml>` - 同步文件到远程 + 提交到远程 Slurm
2. **通过代理提交本地任务**: `ailabber submit local <config.toml>` - 通过代理提交到本地 Slurm
3. **直接调用本地 Slurm**: `ailabber run <config.toml>` - 类似 `uv run`，直接封装调用本地 Slurm，不经过代理

## 架构概述

```
┌─────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   CLI       │ ───► │  Local Proxy    │ ───► │  Remote Server  │
│  (客户端)    │      │  (本地代理)      │      │  (远程服务器)    │
└─────────────┘      └─────────────────┘      └─────────────────┘
       │                     │                         │
       │ (run命令)            ▼                         ▼
       └────────────► ┌─────────────┐          ┌─────────────┐
                      │ Local Slurm │          │ Remote Slurm│
                      │  (本地集群)  │          │  (远程集群)  │
                      └─────────────┘          └─────────────┘
```

### 组件说明

1. **CLI (client/cli.py)**: 命令行客户端
   - `submit remote/local`: 通过代理提交任务
   - `run`: 直接调用本地 Slurm（不经过代理）
   - `status/list/fetch/cancel`: 任务管理

2. **Local Proxy (server/local_proxy.py)**: 本地代理服务器
   - 接收 CLI 请求
   - 本地任务：提交到本地 Slurm
   - 远程任务：rsync 文件 + 调用远程 API
   - 后台轮询任务状态
   - 维护本地数据库

3. **Remote Server (server/remote_server.py)**: 远程服务器
   - 接收任务提交 → 生成并提交 Slurm 脚本
   - 状态查询 → 返回 Slurm 作业状态
   - 文件下载 → 返回日志和结果

## 安装

```bash
# 安装依赖
pip install flask sqlalchemy shortuuid requests

# 或使用 uv
uv sync
```

## 快速开始

### 1. 配置文件

创建 `task_config.toml`:

```toml
[resources]
gpus = 1
cpus = 4
memory = "32G"
time_limit = "4:00:00"

[submit]
upload = "."              # 要同步的目录（仅remote需要）
ignore = [                # 忽略的文件/目录
    "./__pycache__/",
    "./.git/",
    "./.venv/"
]

[run]
workdir = "."             # 工作目录
commands = [              # 执行命令
    "python train.py --config config.yaml"
]

[fetch]
logs = ["./logs"]         # 日志路径
results = ["./output"]    # 结果路径
```

### 2. 使用方式

#### 方式一：直接运行（不经过代理）

```bash
# 直接调用本地 Slurm，类似 uv run
ailabber run task_config.toml
```

#### 方式二：通过代理提交到本地

```bash
# 启动本地代理（另一个终端）
python -m server.local_proxy

# 提交任务
ailabber submit local task_config.toml

# 查看状态
ailabber status <task_id>

# 下载结果
ailabber fetch <task_id>
```

#### 方式三：提交到远程集群

```bash
# 1. 在远程机器启动服务
ssh remote-server
python -m server.remote_server

# 2. 配置 shared/config.py 中的远程服务器地址

# 3. 启动本地代理
python -m server.local_proxy

# 4. 提交任务
ailabber submit remote task_config.toml

# 5. 查看状态和下载结果
ailabber status <task_id>
ailabber fetch <task_id>
```

## 配置说明

编辑 `shared/config.py`:

```python
# 远程服务器配置
REMOTE_SSH_HOST = "your-remote-host"  # 远程服务器地址
REMOTE_SSH_PORT = 22                  # SSH 端口
REMOTE_SSH_USER = "your-username"     # SSH 用户名
REMOTE_BASE_DIR = "/home/username"    # 远程工作目录
```

## CLI 命令

```bash
ailabber help                        # 显示帮助
ailabber whoami                      # 查看当前用户

# 三种任务提交方式
ailabber run <config.toml>           # 直接调用本地 Slurm（不经过代理）
ailabber submit local <config.toml>  # 通过代理提交到本地
ailabber submit remote <config.toml> # 通过代理提交到远程

ailabber status <task_id>            # 查看任务状态
ailabber list [status]               # 列出任务
ailabber fetch <task_id> [dir]       # 下载结果
ailabber cancel <task_id>            # 取消任务
```

## 数据库

- **位置**: `~/.ailabber/local_proxy.db` (SQLite)
- **仅在本地代理**: 数据库只存放在本地，远程服务器无状态
- **表结构**:
  - `users`: 用户信息
  - `tasks`: 任务记录
  - `message_log`: 消息日志

## 注意事项

1. **SSH 配置**: 远程提交需要配置无密码 SSH 登录
2. **Slurm 环境**: 本地和远程都需要安装 Slurm (`sbatch`, `squeue`, `sacct`, `scancel`)
3. **文件同步**: 远程提交会使用 `rsync` 同步文件
4. **轮询间隔**: 默认 5 秒轮询一次远程任务状态

## License

MIT
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