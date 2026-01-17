# AI 课程分布式任务提交系统设计文档

## 1. 系统概述

### 1.1 背景与目标

为 AI 课程设计的任务提交系统，解决以下问题：
- 多学生共用单一远端集群账号
- 本地调试与远端运行的环境一致性
- 文件和数据的双向同步
- 任务追踪与资源统计

### 1.2 核心架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LOCAL (5090 Node)                               │
│  ┌─────────┐      ┌─────────────────────────────────────┐                   │
│  │  CLI    │ ───▶ │         Local Proxy Server          │                   │
│  │(student)│      │  - User session management          │                   │
│  └─────────┘      │  - File cache & sync management     │                   │
│  ┌─────────┐      │  - Task status polling              │                   │
│  │  CLI    │ ───▶ │  - S3 upload/download               │                   │
│  │(student)│      │  - Web UI for status                │                   │
│  └─────────┘      └──────────────┬──────────────────────┘                   │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │   S3 (MinIO)    │
                          │  - sync bucket  │
                          │  - data bucket  │
                          │  - msg queue    │
                          └────────┬────────┘
                                   │
┌──────────────────────────────────┼──────────────────────────────────────────┐
│                              REMOTE CLUSTER                                  │
│                      ┌───────────▼───────────┐                              │
│                      │    Remote Server      │                              │
│                      │  - Task queue mgmt    │                              │
│                      │  - User accounting    │                              │
│                      │  - Env reproduction   │                              │
│                      │  - Slurm submission   │                              │
│                      └───────────┬───────────┘                              │
│                                  │                                          │
│                      ┌───────────▼───────────┐                              │
│                      │    Slurm Cluster      │                              │
│                      └───────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 组件详细设计

### 2.1 CLI (Command Line Interface)

轻量级命令行工具，学生直接使用。

**功能：**
- 用户注册/登录（向 Local Proxy 认证）
- 任务提交（读取配置、打包项目）
- 任务状态查询
- 日志查看
- 结果下载

**命令设计：**
```bash
# 用户管理
ailab register <username>      # 注册用户
ailab login <username>         # 登录（生成本地token）
ailab whoami                   # 查看当前用户

# 任务管理
ailab submit [--config task.toml]  # 提交任务
ailab status [task_id]             # 查看任务状态
ailab list                         # 列出我的任务
ailab logs <task_id>               # 查看日志
ailab cancel <task_id>             # 取消任务

# 数据管理
ailab pull <task_id>               # 拉取任务结果
ailab sync-dataset <local_path>    # 预同步数据集到远端缓存
```

### 2.2 Local Proxy Server

运行在本地 5090 节点上，具有管理员权限，集中处理所有通信。

**功能模块：**

```
Local Proxy Server
├── HTTP API Server (供 CLI 调用)
├── User Manager (本地用户token管理)
├── File Sync Manager
│   ├── Project Sync (uv.lock, pyproject.toml, code)
│   ├── Data Sync (数据集, 额外whl)
│   └── Cache Manager (基于hash的缓存)
├── S3 Client
│   ├── Upload Queue
│   └── Download Queue
├── Message Poller (轮询S3获取状态更新)
├── Task Store (本地SQLite存储任务状态)
└── Web UI (简单状态展示页面)
```

**核心数据结构：**

```python
# 本地任务记录
@dataclass
class LocalTask:
    task_id: str
    username: str
    project_hash: str      # 项目文件hash，用于缓存
    env_hash: str          # 环境hash (uv.lock + pyproject.toml)
    status: str            # pending_upload, uploaded, queued, running, completed, failed
    created_at: datetime
    remote_status: dict    # 从远端同步的状态
    
# 缓存记录
@dataclass  
class CacheEntry:
    hash: str
    s3_key: str
    entry_type: str        # "env" | "project" | "dataset" | "whl"
    size_bytes: int
    last_used: datetime
```

### 2.3 Remote Server

运行在集群节点上，负责实际的任务调度。

**功能模块：**

```
Remote Server
├── S3 Poller (监听新任务请求)
├── Task Processor
│   ├── Environment Builder (uv sync)
│   ├── File Downloader (从S3获取项目和数据)
│   └── Slurm Submitter
├── Task Monitor (监控Slurm任务状态)
├── Result Uploader (上传结果到S3)
├── User Accounting (记录用户使用统计)
└── SQLite Database
```

**用户统计数据：**

```python
@dataclass
class UserStats:
    username: str
    total_tasks: int
    total_gpu_hours: float
    total_cpu_hours: float
    successful_tasks: int
    failed_tasks: int
```

### 2.4 S3 存储结构

```
bucket: ailab-course/
├── messages/
│   ├── to_remote/           # Local → Remote 的消息
│   │   └── {msg_id}.json
│   └── to_local/            # Remote → Local 的消息
│       └── {msg_id}.json
├── envs/
│   └── {env_hash}.tar.gz    # 环境文件打包
├── projects/
│   └── {project_hash}.tar.gz # 项目代码打包
├── datasets/
│   └── {dataset_hash}/      # 数据集（可能较大，按目录组织）
├── whls/
│   └── {whl_hash}.whl       # 额外的wheel文件
├── results/
│   └── {task_id}/           # 任务结果
│       ├── outputs/
│       └── logs/
└── cache_manifest.json      # 全局缓存清单
```

## 3. 任务配置文件设计

### 3.1 task.toml

```toml
[task]
name = "train_resnet"
description = "Training ResNet50 on ImageNet subset"

[resources]
gpus = 1
cpus = 4
memory = "32G"
time_limit = "4:00:00"    # Slurm 时间限制

[environment]
# 环境名称，用于在远端创建/复用虚拟环境
env_name = "my_project_env"
# 额外的 wheel 文件（本地路径）
extra_wheels = [
    "./dist/my_custom_op-0.1.0-cp310-linux_x86_64.whl"
]

[files]
# 需要同步到远端的数据（支持目录和文件）
upload = [
    { local = "./data/train_subset", remote = "data/train" },
    { local = "./configs/", remote = "configs/" },
]
# 需要从远端下载的结果
download = [
    { remote = "checkpoints/", local = "./results/{task_id}/checkpoints/" },
    { remote = "logs/", local = "./results/{task_id}/logs/" },
]

[run]
# 工作目录（相对于同步后的项目根目录）
workdir = "."
# 运行命令
command = "python train.py --config configs/resnet50.yaml"
# 或者使用脚本
# script = "scripts/run.sh"
```

### 3.2 项目结构约定

```
my_project/
├── task.toml              # 任务配置
├── pyproject.toml         # Python 项目配置
├── uv.lock                # uv 锁文件
├── src/                   # 源代码
├── scripts/               # 运行脚本
├── configs/               # 配置文件
└── .ailabignore           # 类似 .gitignore，排除不需要同步的文件
```

## 4. 通信协议设计

由于两端都没有公网，通过 S3 实现消息队列。

### 4.1 消息格式

**任务提交消息 (Local → Remote):**
```json
{
    "msg_type": "submit_task",
    "msg_id": "uuid",
    "timestamp": "2024-01-15T10:30:00Z",
    "payload": {
        "task_id": "task_uuid",
        "username": "student01",
        "env_hash": "sha256:abc123",
        "project_hash": "sha256:def456",
        "data_hashes": ["sha256:ghi789"],
        "whl_hashes": ["sha256:jkl012"],
        "task_config": { /* task.toml 内容 */ }
    }
}
```

**状态更新消息 (Remote → Local):**
```json
{
    "msg_type": "status_update",
    "msg_id": "uuid",
    "timestamp": "2024-01-15T10:35:00Z",
    "payload": {
        "task_id": "task_uuid",
        "status": "running",
        "slurm_job_id": "12345",
        "started_at": "2024-01-15T10:34:00Z",
        "progress": "Epoch 5/100",
        "gpu_hours_used": 0.5
    }
}
```

**任务完成消息 (Remote → Local):**
```json
{
    "msg_type": "task_completed",
    "msg_id": "uuid",
    "timestamp": "2024-01-15T14:30:00Z",
    "payload": {
        "task_id": "task_uuid",
        "status": "completed",
        "result_s3_keys": ["results/task_uuid/checkpoints/", "results/task_uuid/logs/"],
        "total_gpu_hours": 4.0,
        "total_cpu_hours": 16.0,
        "exit_code": 0
    }
}
```

### 4.2 轮询策略

- Local Proxy: 每 10 秒轮询 `messages/to_local/`
- Remote Server: 每 5 秒轮询 `messages/to_remote/`
- 处理后的消息移动到 `messages/processed/` 归档

## 5. 缓存机制设计

### 5.1 缓存层级

```
1. 环境缓存 (env_hash = hash(uv.lock + pyproject.toml))
   - 本地：记录哪些环境已上传
   - 远端：已构建的 venv 目录
   
2. 项目代码缓存 (project_hash = hash(项目文件，排除.ailabignore))
   - 每次提交都检查，相同则跳过上传
   
3. 数据集缓存 (dataset_hash = hash(数据目录))
   - 支持预同步常用数据集
   - 远端保留已下载的数据
   
4. Wheel缓存 (whl_hash = hash(whl文件))
   - 自定义编译的wheel
```

### 5.2 Hash 计算

```python
import hashlib
from pathlib import Path

def compute_dir_hash(path: Path, ignore_patterns: list[str] = None) -> str:
    """计算目录的内容hash"""
    hasher = hashlib.sha256()
    
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file() and not should_ignore(file_path, ignore_patterns):
            # 包含相对路径，保证目录结构变化也能检测
            rel_path = file_path.relative_to(path)
            hasher.update(str(rel_path).encode())
            hasher.update(file_path.read_bytes())
    
    return f"sha256:{hasher.hexdigest()[:16]}"
```

### 5.3 缓存清单

Local Proxy 维护本地缓存清单：
```json
{
    "envs": {
        "sha256:abc123": {
            "s3_key": "envs/sha256:abc123.tar.gz",
            "uploaded_at": "2024-01-15T10:00:00Z",
            "size_bytes": 52428800
        }
    },
    "datasets": {
        "sha256:ghi789": {
            "s3_key": "datasets/sha256:ghi789/",
            "name": "imagenet_subset",
            "uploaded_at": "2024-01-10T08:00:00Z",
            "size_bytes": 1073741824
        }
    }
}
```

## 6. 远端环境复现流程

```
1. 收到任务提交消息
   │
2. 检查环境缓存
   ├── 命中：直接使用已有venv
   └── 未命中：
       ├── 从S3下载 env tarball
       ├── 解压 uv.lock + pyproject.toml
       ├── 创建venv: uv venv /envs/{env_hash}
       └── 安装依赖: uv sync --frozen
   │
3. 下载项目代码（如未缓存）
   │
4. 下载数据文件（如未缓存）
   │
5. 安装额外wheels: uv pip install *.whl
   │
6. 生成Slurm脚本
   │
7. 提交到Slurm: sbatch job.sh
```

**生成的 Slurm 脚本模板：**
```bash
#!/bin/bash
#SBATCH --job-name={task_id}
#SBATCH --gres=gpu:{gpus}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output=/tasks/{task_id}/slurm_%j.out
#SBATCH --error=/tasks/{task_id}/slurm_%j.err

# 激活环境
source /envs/{env_hash}/bin/activate

# 进入工作目录
cd /tasks/{task_id}/project/{workdir}

# 运行命令
{command}

# 记录退出码
echo $? > /tasks/{task_id}/exit_code
```

## 7. Web UI 设计

简单的状态展示页面，运行在 Local Proxy 上。

### 7.1 页面设计

```
┌────────────────────────────────────────────────────────────────┐
│  AI Lab Task Dashboard                          [Refresh] 🔄   │
├────────────────────────────────────────────────────────────────┤
│  Current User: student01          Total GPU Hours: 12.5       │
├────────────────────────────────────────────────────────────────┤
│  My Tasks                                                      │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ ● task_abc123  train_resnet    RUNNING   2.5h   [Logs]  │ │
│  │ ✓ task_def456  eval_model      COMPLETED 0.5h   [Pull]  │ │
│  │ ✗ task_ghi789  debug_run       FAILED    0.1h   [Logs]  │ │
│  │ ◷ task_jkl012  preprocess      QUEUED    -      [Cancel]│ │
│  └──────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────┤
│  All Users (Admin View)                                        │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ User        Active  Queued  GPU Hours  Success Rate     │ │
│  │ student01   1       1       12.5       85%              │ │
│  │ student02   2       0       8.3        90%              │ │
│  │ student03   0       3       5.1        75%              │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

### 7.2 技术选型

- 后端：FastAPI（复用 Local Proxy 的 HTTP Server）
- 前端：简单 HTML + HTMX（避免复杂前端构建）
- 实时更新：SSE 或简单轮询

## 8. 目录结构

### 8.1 项目仓库结构

```
ailab-submit/
├── README.md
├── pyproject.toml
├── cli/                      # CLI 工具
│   ├── __init__.py
│   ├── main.py              # 入口 (click/typer)
│   ├── commands/
│   │   ├── auth.py          # register, login, whoami
│   │   ├── task.py          # submit, status, list, logs, cancel
│   │   └── data.py          # pull, sync-dataset
│   └── config.py            # CLI 配置读取
│
├── proxy/                    # Local Proxy Server
│   ├── __init__.py
│   ├── server.py            # FastAPI 主应用
│   ├── api/
│   │   ├── auth.py          # 用户认证 API
│   │   ├── tasks.py         # 任务管理 API
│   │   └── data.py          # 数据同步 API
│   ├── services/
│   │   ├── user_manager.py
│   │   ├── sync_manager.py
│   │   ├── cache_manager.py
│   │   ├── s3_client.py
│   │   └── message_poller.py
│   ├── models/
│   │   └── schemas.py       # Pydantic models
│   ├── db/
│   │   └── database.py      # SQLite 操作
│   └── web/
│       ├── templates/       # Jinja2 模板
│       └── static/          # CSS/JS
│
├── remote/                   # Remote Server
│   ├── __init__.py
│   ├── server.py            # 主循环
│   ├── services/
│   │   ├── task_processor.py
│   │   ├── env_builder.py
│   │   ├── slurm_submitter.py
│   │   ├── task_monitor.py
│   │   ├── result_uploader.py
│   │   └── accounting.py
│   ├── models/
│   │   └── schemas.py
│   └── db/
│       └── database.py
│
├── common/                   # 共享代码
│   ├── __init__.py
│   ├── s3.py                # S3 操作封装
│   ├── hash.py              # Hash 计算
│   ├── models.py            # 共享数据模型
│   └── constants.py         # 常量定义
│
└── tests/
    ├── test_cli/
    ├── test_proxy/
    └── test_remote/
```

## 9. 实现优先级与路线图

### Phase 1: 最小可用版本 (MVP)

**目标：能跑通基本流程**

1. CLI 基础命令：`register`, `login`, `submit`, `status`, `list`
2. Local Proxy：
   - 用户管理（简单token）
   - 文件打包上传到 S3
   - 消息发送/接收
3. Remote Server：
   - 消息轮询
   - 环境构建（uv sync）
   - Slurm 提交
   - 状态回报
4. 基本缓存：环境缓存

**预计工作量：2-3天**

### Phase 2: 完善功能

1. CLI：`logs`, `cancel`, `pull`
2. 项目代码缓存
3. 数据集缓存与预同步
4. Web UI 基础版
5. 用户统计

**预计工作量：2-3天**

### Phase 3: 优化体验

1. 更好的进度显示
2. 缓存清理策略
3. 错误处理与重试
4. 管理员功能（查看所有用户、清理任务等）

**预计工作量：1-2天**

## 10. 配置文件

### 10.1 Local Proxy 配置 (proxy_config.toml)

```toml
[server]
host = "0.0.0.0"
port = 8800

[s3]
endpoint = "http://minio.internal:9000"
access_key = "minioadmin"
secret_key = "minioadmin"
bucket = "ailab-course"

[polling]
interval_seconds = 10

[database]
path = "/var/lib/ailab-proxy/tasks.db"

[cache]
max_size_gb = 100
cleanup_threshold = 0.9  # 90%时触发清理
```

### 10.2 Remote Server 配置 (remote_config.toml)

```toml
[s3]
endpoint = "http://minio.internal:9000"
access_key = "minioadmin"
secret_key = "minioadmin"
bucket = "ailab-course"

[polling]
interval_seconds = 5

[paths]
envs_dir = "/data/ailab/envs"
tasks_dir = "/data/ailab/tasks"
cache_dir = "/data/ailab/cache"

[slurm]
partition = "gpu"
default_qos = "normal"

[database]
path = "/data/ailab/accounting.db"
```

## 11. 安全考虑

### 11.1 用户隔离

- 每个用户只能看到自己的任务
- 文件系统隔离：每个任务在独立目录运行
- 资源配额：可以限制每用户的 GPU hours

### 11.2 简化的认证

MVP阶段使用简单方案：
- 注册时生成随机 token
- Token 存储在 `~/.ailab/credentials`
- Local Proxy 验证 token

后续可以升级为更安全的方案（JWT等）

## 12. 总结

这个设计的核心思路是：

1. **三层架构**：CLI（轻量客户端）→ Local Proxy（重型本地服务）→ Remote Server（集群服务）
2. **S3 作为通信中枢**：解决两端无公网的问题
3. **基于 Hash 的缓存**：减少重复传输
4. **uv 作为环境管理**：简化环境复现
5. **渐进式实现**：先跑通核心流程，再完善功能

