# ailabber

AI Lab 分布式任务提交系统 - 为 AI 课程设计的 GPU 集群任务管理工具。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         LOCAL (5090 Node)                        │
│                                                                  │
│   ┌─────────┐         ┌─────────────────────────────┐           │
│   │   CLI   │ ──────▶ │     Local Proxy Server      │           │
│   │(student)│  HTTP   │   - 用户会话管理             │           │
│   └─────────┘         │   - 文件缓存与同步           │           │
│                       │   - 任务状态轮询             │           │
│                       └──────────────┬──────────────┘           │
└──────────────────────────────────────┼──────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │  rsync/frp      │
                              └────────┬────────┘
                                       │
┌──────────────────────────────────────┼──────────────────────────┐
│                           REMOTE CLUSTER                        │
│                      ┌───────────────▼───────────────┐          │
│                      │       Remote Server           │          │
│                      │   - 任务队列管理                │          │
│                      │   - 环境复现                   │          │
│                      │   - Slurm 任务提交             │          │
│                      └───────────────┬───────────────┘          │
│                                      │                          │
│                      ┌───────────────▼───────────────┐          │
│                      │        Slurm Cluster          │          │
│                      └───────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
ailabber/
├── client/
│   └── cli.py              # 命令行客户端
├── server/
│   ├── local_proxy.py      # 本地代理服务器 (Flask)
│   └── remote_server.py    # 远程服务器
├── shared/
│   ├── config.py           # 配置常量
│   ├── database.py         # 数据库 ORM 模型
│   └── logger.py           # 日志配置
├── utils/
│   └── db_init.py          # 数据库初始化工具
├── task_config.toml        # 任务配置示例
├── pyproject.toml          # 项目依赖
└── README.md
```

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd ailabber

# 使用 uv 安装依赖
uv sync
```

## 快速开始

### 1. 启动本地代理服务器

```bash
python -m server.local_proxy
```

服务器默认运行在 `http://127.0.0.1:8080`

### 2. 使用 CLI 提交任务

```bash
# 查看当前用户
python -m client.cli whoami

# 提交任务（使用当前目录的 task_config.toml）
python -m client.cli submit

# 提交任务（指定配置文件）
python -m client.cli submit ./my_task_config.toml

# 查看任务状态
python -m client.cli status <task_id>

# 列出所有任务
python -m client.cli list

# 下载任务日志和结果
python -m client.cli fetch <task_id>

# 取消任务
python -m client.cli cancel <task_id>

# 显示帮助
python -m client.cli help
```

## 任务配置

创建 `task_config.toml` 文件来配置任务：

```toml
[resources]
gpus = 1                      # GPU 数量
cpus = 4                      # CPU 核心数
memory = "32G"                # 内存限制
time_limit = "4:00:00"        # 运行时间限制

[environment]
pyproject_toml = "./pyproject.toml"   # 项目配置
uv_lock = "./uv.lock"                 # 锁文件
extra_wheels = [                       # 额外的 wheel 包
    "./dist/my_custom_op-0.1.0-cp310-linux_x86_64.whl"
]

[files]
upload = "."                  # 上传目录
ignore = [                    # 忽略的文件/目录
    "./__pycache__/"
]
workdir = "."                 # 工作目录

[run]
commands = [                  # 运行命令
    "python train.py --config configs/resnet50.yaml"
]
logs = ["./logs"]             # 日志目录
results = ["./output"]        # 结果目录
```

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/submit` | POST | 提交新任务 |
| `/api/status/<task_id>` | GET | 获取任务状态 |
| `/api/tasks` | GET | 列出用户任务 |
| `/api/logs/<task_id>` | GET | 下载任务日志 |
| `/api/cancel/<task_id>` | POST | 取消/终止任务 |
| `/health` | GET | 健康检查 |

## 任务状态

| 状态 | 描述 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在运行 |
| `completed` | 执行完成 |
| `failed` | 执行失败 |
| `canceled` | 已取消（未开始） |
| `terminated` | 已终止（运行中取消） |

## 配置说明

配置文件位于 `shared/config.py`：

```python
# 服务端口
LOCAL_PROXY_PORT = 8080       # 本地代理端口
REMOTE_SERVER_PORT = 8080     # 远程服务器端口

# 数据目录
DATA_DIR = ~/.ailabber        # 数据存储目录
LOCAL_DB_PATH = ~/.ailabber/local_proxy.db   # 本地数据库
```

## 依赖

- Python >= 3.10
- Flask >= 3.1
- Requests >= 2.32
- SQLAlchemy >= 2.0

## License

MIT
