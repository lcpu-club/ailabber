# AILabber - AI课程分布式任务提交系统

## 项目结构

```
ailabber/
├── shared/              # 共享模块
│   ├── models.py        # 数据模型 (Task, Message, User)
│   ├── config.py        # 配置常量
│   └── logger.py        # 日志模块
├── client/
│   └── cli.py           # 命令行客户端
├── server/
│   ├── local_proxy.py   # 本地代理服务器
│   └── remote_server.py # 远端执行服务器
└── pyproject.toml       # 项目配置
```

## 安装

```bash
# 开发模式安装
uv pip install -e .
```

## 快速开始

### 1. 启动本地代理服务器

```bash
ailabber-proxy
```

### 2. 启动远端服务器 (另一个终端)

```bash
ailabber-remote
```

### 3. 使用 CLI

```bash
# 查看当前用户 (基于 SSH 公钥自动识别)
ailabber whoami

# 提交任务
ailabber submit echo "hello world"
ailabber submit python -c "print('hello')"

# 查看任务列表
ailabber list

# 查看任务状态
ailabber status <task_id>

# 查看日志
ailabber logs <task_id>

# 取消任务
ailabber cancel <task_id>
```

## 系统架构

```
┌─────────────┐     HTTP      ┌─────────────────┐     消息队列      ┌───────────────┐
│   CLI       │ ───────────▶  │  Local Proxy    │ ──────────────▶   │ Remote Server │
│  (学生使用)  │               │  (SQLite存储)    │                   │  (任务执行)    │
└─────────────┘               │  (用户/任务管理)  │  ◀──────────────   └───────────────┘
                              └─────────────────┘     状态更新
```

## 工作流程

1. CLI 通过 HTTP 请求发送命令到 Local Proxy
2. Local Proxy 将任务消息写入 `~/.ailabber/messages/to_remote/`
3. Remote Server 轮询该目录，获取任务并执行
4. Remote Server 将结果写入 `~/.ailabber/messages/to_local/`
5. Local Proxy 轮询该目录，更新任务状态

## 数据存储

所有数据存储在 `~/.ailabber/` 目录下：
- `local_proxy.db` - SQLite 数据库 (用户和任务信息)
- `messages/` - 消息队列目录
- `results/` - 任务执行结果
- `logs/` - 日志文件

## 开发笔记

当前版本是基础框架实现，后续需要添加：
- [ ] S3 存储集成（替代本地文件系统）
- [ ] 项目文件打包和同步
- [ ] 环境复现 (uv sync)
- [ ] Slurm 集成
- [ ] Web UI 状态展示
- [ ] 缓存机制
