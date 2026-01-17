# AI 课程分布式任务提交系统设计文档 (Rust 版)

## 1. 系统概述

### 1.1 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LOCAL (5090 Node)                               │
│  ┌─────────┐      ┌─────────────────────────────────────┐                   │
│  │  CLI    │ ───▶ │         Local Proxy Server          │                   │
│  │(student)│ gRPC │  - User session management          │                   │
│  └─────────┘  or  │  - File cache & sync management     │                   │
│  ┌─────────┐ HTTP │  - Task status polling              │                   │
│  │  CLI    │ ───▶ │  - Transport client                 │                   │
│  │(student)│      │  - Web UI for status                │                   │
│  └─────────┘      └──────────────┬──────────────────────┘                   │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Transport Layer (trait)   │
                    │  ┌────────┐ ┌────────────┐  │
                    │  │   S3   │ │   Redis    │  │
                    │  │ (MinIO)│ │  Pub/Sub   │  │
                    │  └────────┘ └────────────┘  │
                    │  ┌────────┐ ┌────────────┐  │
                    │  │  HTTP  │ │    NATS    │  │
                    │  │ Polling│ │            │  │
                    │  └────────┘ └────────────┘  │
                    └──────────────┬──────────────┘
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

### 1.2 核心设计原则

1. **Transport 抽象**：控制面通信通过 trait 抽象，支持多种后端
2. **Data Plane 与 Control Plane 分离**：
   - Control Plane: 消息、状态、命令（走 Transport）
   - Data Plane: 大文件传输（始终走对象存储）
3. **Workspace 组织**：多 crate 结构，共享核心类型

## 2. Rust 项目结构

### 2.1 Workspace 布局

```
ailab/
├── Cargo.toml                    # Workspace root
├── README.md
├── config/                       # 配置文件示例
│   ├── proxy.example.toml
│   └── remote.example.toml
│
├── crates/
│   ├── ailab-core/              # 核心类型和 trait 定义
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── types/           # 共享数据类型
│   │       │   ├── mod.rs
│   │       │   ├── task.rs
│   │       │   ├── user.rs
│   │       │   └── message.rs
│   │       ├── transport/       # Transport trait 定义
│   │       │   ├── mod.rs
│   │       │   └── traits.rs
│   │       ├── storage/         # Storage trait 定义
│   │       │   ├── mod.rs
│   │       │   └── traits.rs
│   │       ├── hash.rs          # Hash 计算工具
│   │       └── error.rs         # 统一错误类型
│   │
│   ├── ailab-transport/         # Transport 实现
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── s3.rs            # S3/MinIO 实现
│   │       ├── redis.rs         # Redis Pub/Sub 实现
│   │       ├── http.rs          # HTTP 长轮询实现
│   │       └── nats.rs          # NATS 实现 (可选)
│   │
│   ├── ailab-storage/           # 对象存储实现
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── s3.rs            # S3 兼容存储
│   │       └── local.rs         # 本地文件系统 (测试用)
│   │
│   ├── ailab-cli/               # CLI 工具
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── main.rs
│   │       ├── commands/
│   │       │   ├── mod.rs
│   │       │   ├── auth.rs
│   │       │   ├── task.rs
│   │       │   └── data.rs
│   │       └── config.rs
│   │
│   ├── ailab-proxy/             # Local Proxy Server
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── main.rs
│   │       ├── server.rs        # Axum HTTP server
│   │       ├── api/
│   │       │   ├── mod.rs
│   │       │   ├── auth.rs
│   │       │   ├── tasks.rs
│   │       │   └── data.rs
│   │       ├── services/
│   │       │   ├── mod.rs
│   │       │   ├── user.rs
│   │       │   ├── sync.rs
│   │       │   ├── cache.rs
│   │       │   └── poller.rs
│   │       ├── db/
│   │       │   └── mod.rs       # SQLite via sqlx
│   │       └── web/
│   │           ├── mod.rs
│   │           ├── templates/   # Askama 模板
│   │           └── handlers.rs
│   │
│   └── ailab-remote/            # Remote Server
│       ├── Cargo.toml
│       └── src/
│           ├── main.rs
│           ├── server.rs
│           ├── services/
│           │   ├── mod.rs
│           │   ├── processor.rs
│           │   ├── env_builder.rs
│           │   ├── slurm.rs
│           │   ├── monitor.rs
│           │   └── accounting.rs
│           └── db/
│               └── mod.rs
│
└── tests/                       # 集成测试
    └── integration/
```

### 2.2 Workspace Cargo.toml

```toml
[workspace]
resolver = "2"
members = [
    "crates/ailab-core",
    "crates/ailab-transport",
    "crates/ailab-storage",
    "crates/ailab-cli",
    "crates/ailab-proxy",
    "crates/ailab-remote",
]

[workspace.package]
version = "0.1.0"
edition = "2021"
license = "MIT"
repository = "https://github.com/yourorg/ailab"

[workspace.dependencies]
# Async runtime
tokio = { version = "1", features = ["full"] }

# Serialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"
toml = "0.8"

# HTTP & API
axum = { version = "0.7", features = ["macros"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["cors", "trace"] }
reqwest = { version = "0.12", features = ["json", "rustls-tls"], default-features = false }

# CLI
clap = { version = "4", features = ["derive"] }

# Database
sqlx = { version = "0.8", features = ["runtime-tokio", "sqlite"] }

# S3
aws-sdk-s3 = "1"
aws-config = "1"

# Redis
redis = { version = "0.25", features = ["tokio-comp", "connection-manager"] }

# Logging & Tracing
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

# Utils
uuid = { version = "1", features = ["v4", "serde"] }
chrono = { version = "0.4", features = ["serde"] }
sha2 = "0.10"
hex = "0.4"
thiserror = "1"
anyhow = "1"
async-trait = "0.1"
futures = "0.3"
walkdir = "2"
ignore = "0.4"  # For .gitignore-style patterns
tar = "0.4"
flate2 = "1"
directories = "5"  # For XDG paths
indicatif = "0.17"  # Progress bars

# Template
askama = "0.12"
askama_axum = "0.4"
```

## 3. 核心类型定义 (ailab-core)

### 3.1 Transport Trait

```rust
// crates/ailab-core/src/transport/traits.rs

use async_trait::async_trait;
use crate::types::message::{ControlMessage, MessageId};
use crate::error::Result;

/// 控制面消息传输的方向
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Channel {
    /// Local Proxy -> Remote Server
    ToRemote,
    /// Remote Server -> Local Proxy  
    ToLocal,
}

/// 控制面传输层抽象
/// 
/// 用于传输小型控制消息（任务提交、状态更新等）
/// 大文件传输应使用 Storage trait
#[async_trait]
pub trait Transport: Send + Sync + 'static {
    /// 发送消息到指定通道
    async fn send(&self, channel: Channel, message: ControlMessage) -> Result<MessageId>;
    
    /// 从指定通道接收消息（阻塞直到有消息或超时）
    /// 返回 None 表示超时无消息
    async fn receive(&self, channel: Channel, timeout: std::time::Duration) -> Result<Option<ControlMessage>>;
    
    /// 确认消息已处理（用于实现 at-least-once 语义）
    async fn ack(&self, channel: Channel, message_id: &MessageId) -> Result<()>;
    
    /// 获取未确认的消息列表（用于恢复）
    async fn list_pending(&self, channel: Channel) -> Result<Vec<ControlMessage>>;
}

/// Transport 工厂，用于根据配置创建实例
pub trait TransportFactory {
    fn create(config: &TransportConfig) -> Result<Box<dyn Transport>>;
}

#[derive(Debug, Clone, serde::Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum TransportConfig {
    S3 {
        endpoint: String,
        bucket: String,
        access_key: String,
        secret_key: String,
        region: Option<String>,
        prefix: Option<String>,
        poll_interval_ms: Option<u64>,
    },
    Redis {
        url: String,
        prefix: Option<String>,
    },
    Http {
        /// 对方的 HTTP 端点（需要有一端有公网）
        endpoint: String,
        /// 认证 token
        token: Option<String>,
    },
    Nats {
        url: String,
        subject_prefix: Option<String>,
    },
}
```

### 3.2 Storage Trait

```rust
// crates/ailab-core/src/storage/traits.rs

use async_trait::async_trait;
use std::path::Path;
use tokio::io::{AsyncRead, AsyncWrite};
use crate::error::Result;

/// 对象存储抽象（用于大文件传输）
#[async_trait]
pub trait Storage: Send + Sync + 'static {
    /// 上传文件
    async fn upload(&self, key: &str, path: &Path) -> Result<()>;
    
    /// 上传目录（打包为 tar.gz）
    async fn upload_dir(&self, key: &str, path: &Path, ignore_patterns: &[String]) -> Result<()>;
    
    /// 下载文件
    async fn download(&self, key: &str, path: &Path) -> Result<()>;
    
    /// 下载并解压目录
    async fn download_dir(&self, key: &str, path: &Path) -> Result<()>;
    
    /// 检查对象是否存在
    async fn exists(&self, key: &str) -> Result<bool>;
    
    /// 删除对象
    async fn delete(&self, key: &str) -> Result<()>;
    
    /// 列出指定前缀的对象
    async fn list(&self, prefix: &str) -> Result<Vec<String>>;
    
    /// 获取对象大小
    async fn size(&self, key: &str) -> Result<u64>;
    
    /// 获取流式读取器（用于大文件）
    async fn get_reader(&self, key: &str) -> Result<Box<dyn AsyncRead + Unpin + Send>>;
    
    /// 获取流式写入器
    async fn get_writer(&self, key: &str) -> Result<Box<dyn AsyncWrite + Unpin + Send>>;
}

#[derive(Debug, Clone, serde::Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum StorageConfig {
    S3 {
        endpoint: String,
        bucket: String,
        access_key: String,
        secret_key: String,
        region: Option<String>,
    },
    Local {
        root: String,
    },
}
```

### 3.3 核心数据类型

```rust
// crates/ailab-core/src/types/task.rs

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

pub type TaskId = Uuid;
pub type UserId = String;
pub type ContentHash = String;  // "sha256:xxxx"

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskConfig {
    pub name: String,
    pub description: Option<String>,
    pub resources: ResourceRequest,
    pub environment: EnvironmentConfig,
    pub files: FileMapping,
    pub run: RunConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceRequest {
    pub gpus: u32,
    pub cpus: u32,
    pub memory: String,         // "32G"
    pub time_limit: String,     // "4:00:00"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentConfig {
    pub env_name: String,
    #[serde(default)]
    pub extra_wheels: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMapping {
    #[serde(default)]
    pub upload: Vec<PathMapping>,
    #[serde(default)]
    pub download: Vec<PathMapping>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathMapping {
    pub local: String,
    pub remote: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunConfig {
    #[serde(default = "default_workdir")]
    pub workdir: String,
    pub command: Option<String>,
    pub script: Option<String>,
}

fn default_workdir() -> String {
    ".".to_string()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    /// 正在上传文件到存储
    Uploading,
    /// 已上传，等待远端处理
    Pending,
    /// 远端正在准备环境
    Preparing,
    /// 已提交到 Slurm，排队中
    Queued,
    /// Slurm 任务正在运行
    Running,
    /// 任务完成，结果待下载
    Completed,
    /// 任务失败
    Failed,
    /// 任务被取消
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: TaskId,
    pub user_id: UserId,
    pub config: TaskConfig,
    pub status: TaskStatus,
    
    // Hashes for caching
    pub env_hash: ContentHash,
    pub project_hash: ContentHash,
    pub data_hashes: Vec<ContentHash>,
    pub whl_hashes: Vec<ContentHash>,
    
    // Timestamps
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    
    // Remote info
    pub slurm_job_id: Option<String>,
    pub exit_code: Option<i32>,
    pub error_message: Option<String>,
    
    // Resource usage
    pub gpu_seconds: Option<u64>,
    pub cpu_seconds: Option<u64>,
}
```

### 3.4 控制消息类型

```rust
// crates/ailab-core/src/types/message.rs

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use super::task::{Task, TaskId, TaskStatus, ContentHash, UserId};

pub type MessageId = Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ControlMessage {
    pub id: MessageId,
    pub timestamp: DateTime<Utc>,
    pub payload: MessagePayload,
}

impl ControlMessage {
    pub fn new(payload: MessagePayload) -> Self {
        Self {
            id: Uuid::new_v4(),
            timestamp: Utc::now(),
            payload,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MessagePayload {
    // ===== Local -> Remote =====
    
    /// 提交新任务
    SubmitTask {
        task: Task,
        /// 存储中的路径映射
        storage_keys: StorageKeys,
    },
    
    /// 取消任务
    CancelTask {
        task_id: TaskId,
        user_id: UserId,
    },
    
    /// 查询任务状态（用于同步）
    QueryStatus {
        task_ids: Vec<TaskId>,
    },
    
    // ===== Remote -> Local =====
    
    /// 任务状态更新
    StatusUpdate {
        task_id: TaskId,
        status: TaskStatus,
        slurm_job_id: Option<String>,
        progress: Option<String>,
        error_message: Option<String>,
    },
    
    /// 任务完成通知
    TaskCompleted {
        task_id: TaskId,
        status: TaskStatus,  // Completed | Failed | Cancelled
        exit_code: Option<i32>,
        result_keys: Vec<String>,  // 结果文件在存储中的 key
        gpu_seconds: u64,
        cpu_seconds: u64,
        error_message: Option<String>,
    },
    
    /// 批量状态响应
    StatusResponse {
        tasks: Vec<TaskStatusInfo>,
    },
    
    // ===== Bidirectional =====
    
    /// 心跳/健康检查
    Heartbeat {
        source: String,  // "proxy" | "remote"
        timestamp: DateTime<Utc>,
    },
    
    /// ACK 确认
    Ack {
        message_id: MessageId,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StorageKeys {
    pub env: String,           // envs/{env_hash}.tar.gz
    pub project: String,       // projects/{project_hash}.tar.gz
    pub data: Vec<String>,     // datasets/{hash}/
    pub whls: Vec<String>,     // whls/{hash}.whl
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskStatusInfo {
    pub task_id: TaskId,
    pub status: TaskStatus,
    pub slurm_job_id: Option<String>,
    pub progress: Option<String>,
    pub gpu_seconds: Option<u64>,
}
```

### 3.5 Hash 计算

```rust
// crates/ailab-core/src/hash.rs

use sha2::{Sha256, Digest};
use std::path::Path;
use walkdir::WalkDir;
use ignore::gitignore::GitignoreBuilder;
use crate::error::Result;

const HASH_PREFIX: &str = "sha256";
const HASH_LENGTH: usize = 16;  // 使用前16个字符

/// 计算文件的 hash
pub fn hash_file(path: &Path) -> Result<String> {
    let content = std::fs::read(path)?;
    Ok(hash_bytes(&content))
}

/// 计算字节的 hash
pub fn hash_bytes(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    let result = hasher.finalize();
    format!("{}:{}", HASH_PREFIX, hex::encode(&result[..HASH_LENGTH/2]))
}

/// 计算目录的 hash（考虑 ignore 模式）
pub fn hash_directory(path: &Path, ignore_patterns: &[String]) -> Result<String> {
    let mut hasher = Sha256::new();
    
    // 构建 ignore 匹配器
    let mut builder = GitignoreBuilder::new(path);
    for pattern in ignore_patterns {
        builder.add_line(None, pattern)?;
    }
    let ignore = builder.build()?;
    
    // 遍历目录，按路径排序保证一致性
    let mut entries: Vec<_> = WalkDir::new(path)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
        .filter(|e| {
            ignore.matched(e.path(), false).is_none()
        })
        .collect();
    
    entries.sort_by_key(|e| e.path().to_path_buf());
    
    for entry in entries {
        let rel_path = entry.path().strip_prefix(path)?;
        // 包含相对路径
        hasher.update(rel_path.to_string_lossy().as_bytes());
        // 包含文件内容
        hasher.update(&std::fs::read(entry.path())?);
    }
    
    let result = hasher.finalize();
    Ok(format!("{}:{}", HASH_PREFIX, hex::encode(&result[..HASH_LENGTH/2])))
}

/// 计算环境 hash (uv.lock + pyproject.toml)
pub fn hash_environment(project_dir: &Path) -> Result<String> {
    let mut hasher = Sha256::new();
    
    let uv_lock = project_dir.join("uv.lock");
    let pyproject = project_dir.join("pyproject.toml");
    
    if uv_lock.exists() {
        hasher.update(b"uv.lock:");
        hasher.update(&std::fs::read(&uv_lock)?);
    }
    
    if pyproject.exists() {
        hasher.update(b"pyproject.toml:");
        hasher.update(&std::fs::read(&pyproject)?);
    }
    
    let result = hasher.finalize();
    Ok(format!("{}:{}", HASH_PREFIX, hex::encode(&result[..HASH_LENGTH/2])))
}
```

## 4. Transport 实现 (ailab-transport)

### 4.1 S3 Transport

```rust
// crates/ailab-transport/src/s3.rs

use ailab_core::{
    transport::{Transport, Channel, TransportConfig},
    types::message::{ControlMessage, MessageId},
    error::Result,
};
use async_trait::async_trait;
use aws_sdk_s3::Client;
use std::time::Duration;
use tokio::time::sleep;

pub struct S3Transport {
    client: Client,
    bucket: String,
    prefix: String,
    poll_interval: Duration,
}

impl S3Transport {
    pub async fn new(config: &TransportConfig) -> Result<Self> {
        let TransportConfig::S3 {
            endpoint,
            bucket,
            access_key,
            secret_key,
            region,
            prefix,
            poll_interval_ms,
        } = config else {
            anyhow::bail!("Expected S3 config");
        };
        
        let sdk_config = aws_config::from_env()
            .endpoint_url(endpoint)
            .credentials_provider(aws_sdk_s3::config::Credentials::new(
                access_key,
                secret_key,
                None,
                None,
                "static",
            ))
            .region(aws_sdk_s3::config::Region::new(
                region.clone().unwrap_or_else(|| "us-east-1".to_string())
            ))
            .load()
            .await;
        
        let client = Client::new(&sdk_config);
        
        Ok(Self {
            client,
            bucket: bucket.clone(),
            prefix: prefix.clone().unwrap_or_else(|| "messages".to_string()),
            poll_interval: Duration::from_millis(poll_interval_ms.unwrap_or(1000)),
        })
    }
    
    fn channel_prefix(&self, channel: Channel) -> String {
        let dir = match channel {
            Channel::ToRemote => "to_remote",
            Channel::ToLocal => "to_local",
        };
        format!("{}/{}", self.prefix, dir)
    }
    
    fn message_key(&self, channel: Channel, id: &MessageId) -> String {
        format!("{}/{}.json", self.channel_prefix(channel), id)
    }
    
    fn processed_key(&self, channel: Channel, id: &MessageId) -> String {
        format!("{}/processed/{}.json", self.channel_prefix(channel), id)
    }
}

#[async_trait]
impl Transport for S3Transport {
    async fn send(&self, channel: Channel, message: ControlMessage) -> Result<MessageId> {
        let key = self.message_key(channel, &message.id);
        let body = serde_json::to_vec(&message)?;
        
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(&key)
            .body(body.into())
            .content_type("application/json")
            .send()
            .await?;
        
        Ok(message.id)
    }
    
    async fn receive(&self, channel: Channel, timeout: Duration) -> Result<Option<ControlMessage>> {
        let prefix = self.channel_prefix(channel);
        let deadline = tokio::time::Instant::now() + timeout;
        
        loop {
            // 列出消息
            let response = self.client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(&prefix)
                .max_keys(10)
                .send()
                .await?;
            
            if let Some(contents) = response.contents {
                for object in contents {
                    let key = object.key.unwrap_or_default();
                    // 跳过 processed 目录
                    if key.contains("/processed/") {
                        continue;
                    }
                    
                    // 获取消息内容
                    let get_response = self.client
                        .get_object()
                        .bucket(&self.bucket)
                        .key(&key)
                        .send()
                        .await?;
                    
                    let body = get_response.body.collect().await?.into_bytes();
                    let message: ControlMessage = serde_json::from_slice(&body)?;
                    
                    return Ok(Some(message));
                }
            }
            
            // 检查超时
            if tokio::time::Instant::now() >= deadline {
                return Ok(None);
            }
            
            sleep(self.poll_interval).await;
        }
    }
    
    async fn ack(&self, channel: Channel, message_id: &MessageId) -> Result<()> {
        let src_key = self.message_key(channel, message_id);
        let dst_key = self.processed_key(channel, message_id);
        
        // 移动到 processed 目录
        self.client
            .copy_object()
            .bucket(&self.bucket)
            .copy_source(format!("{}/{}", self.bucket, src_key))
            .key(&dst_key)
            .send()
            .await?;
        
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(&src_key)
            .send()
            .await?;
        
        Ok(())
    }
    
    async fn list_pending(&self, channel: Channel) -> Result<Vec<ControlMessage>> {
        let prefix = format!("{}/", self.channel_prefix(channel));
        let mut messages = Vec::new();
        
        let response = self.client
            .list_objects_v2()
            .bucket(&self.bucket)
            .prefix(&prefix)
            .send()
            .await?;
        
        if let Some(contents) = response.contents {
            for object in contents {
                let key = object.key.unwrap_or_default();
                if key.contains("/processed/") {
                    continue;
                }
                
                let get_response = self.client
                    .get_object()
                    .bucket(&self.bucket)
                    .key(&key)
                    .send()
                    .await?;
                
                let body = get_response.body.collect().await?.into_bytes();
                let message: ControlMessage = serde_json::from_slice(&body)?;
                messages.push(message);
            }
        }
        
        Ok(messages)
    }
}
```

### 4.2 Redis Transport

```rust
// crates/ailab-transport/src/redis.rs

use ailab_core::{
    transport::{Transport, Channel, TransportConfig},
    types::message::{ControlMessage, MessageId},
    error::Result,
};
use async_trait::async_trait;
use redis::AsyncCommands;
use std::time::Duration;

pub struct RedisTransport {
    client: redis::Client,
    prefix: String,
}

impl RedisTransport {
    pub async fn new(config: &TransportConfig) -> Result<Self> {
        let TransportConfig::Redis { url, prefix } = config else {
            anyhow::bail!("Expected Redis config");
        };
        
        let client = redis::Client::open(url.as_str())?;
        
        Ok(Self {
            client,
            prefix: prefix.clone().unwrap_or_else(|| "ailab".to_string()),
        })
    }
    
    fn queue_key(&self, channel: Channel) -> String {
        let dir = match channel {
            Channel::ToRemote => "to_remote",
            Channel::ToLocal => "to_local",
        };
        format!("{}:queue:{}", self.prefix, dir)
    }
    
    fn processing_key(&self, channel: Channel) -> String {
        let dir = match channel {
            Channel::ToRemote => "to_remote",
            Channel::ToLocal => "to_local",
        };
        format!("{}:processing:{}", self.prefix, dir)
    }
}

#[async_trait]
impl Transport for RedisTransport {
    async fn send(&self, channel: Channel, message: ControlMessage) -> Result<MessageId> {
        let mut conn = self.client.get_multiplexed_async_connection().await?;
        let queue_key = self.queue_key(channel);
        let data = serde_json::to_string(&message)?;
        
        conn.rpush::<_, _, ()>(&queue_key, &data).await?;
        
        Ok(message.id)
    }
    
    async fn receive(&self, channel: Channel, timeout: Duration) -> Result<Option<ControlMessage>> {
        let mut conn = self.client.get_multiplexed_async_connection().await?;
        let queue_key = self.queue_key(channel);
        let processing_key = self.processing_key(channel);
        
        // BLMOVE: 原子地从队列移动到处理中列表
        let result: Option<String> = redis::cmd("BLMOVE")
            .arg(&queue_key)
            .arg(&processing_key)
            .arg("LEFT")
            .arg("RIGHT")
            .arg(timeout.as_secs_f64())
            .query_async(&mut conn)
            .await?;
        
        match result {
            Some(data) => {
                let message: ControlMessage = serde_json::from_str(&data)?;
                Ok(Some(message))
            }
            None => Ok(None),
        }
    }
    
    async fn ack(&self, channel: Channel, message_id: &MessageId) -> Result<()> {
        let mut conn = self.client.get_multiplexed_async_connection().await?;
        let processing_key = self.processing_key(channel);
        
        // 从 processing 列表中删除已确认的消息
        // 需要遍历找到对应的消息
        let items: Vec<String> = conn.lrange(&processing_key, 0, -1).await?;
        
        for item in items {
            let msg: ControlMessage = serde_json::from_str(&item)?;
            if msg.id == *message_id {
                conn.lrem::<_, _, ()>(&processing_key, 1, &item).await?;
                break;
            }
        }
        
        Ok(())
    }
    
    async fn list_pending(&self, channel: Channel) -> Result<Vec<ControlMessage>> {
        let mut conn = self.client.get_multiplexed_async_connection().await?;
        let queue_key = self.queue_key(channel);
        
        let items: Vec<String> = conn.lrange(&queue_key, 0, -1).await?;
        
        items
            .into_iter()
            .map(|s| Ok(serde_json::from_str(&s)?))
            .collect()
    }
}
```

### 4.3 Transport 工厂

```rust
// crates/ailab-transport/src/lib.rs

mod s3;
mod redis;
mod http;

pub use s3::S3Transport;
pub use redis::RedisTransport;
pub use http::HttpTransport;

use ailab_core::{
    transport::{Transport, TransportConfig},
    error::Result,
};

pub async fn create_transport(config: &TransportConfig) -> Result<Box<dyn Transport>> {
    match config {
        TransportConfig::S3 { .. } => {
            Ok(Box::new(S3Transport::new(config).await?))
        }
        TransportConfig::Redis { .. } => {
            Ok(Box::new(RedisTransport::new(config).await?))
        }
        TransportConfig::Http { .. } => {
            Ok(Box::new(HttpTransport::new(config).await?))
        }
        TransportConfig::Nats { .. } => {
            anyhow::bail!("NATS transport not implemented yet")
        }
    }
}
```

## 5. CLI 设计 (ailab-cli)

### 5.1 命令结构

```rust
// crates/ailab-cli/src/main.rs

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "ailab")]
#[command(about = "AI Lab task submission CLI")]
#[command(version)]
struct Cli {
    /// Proxy server address
    #[arg(long, env = "AILAB_PROXY_URL", default_value = "http://localhost:8800")]
    proxy_url: String,
    
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// User authentication
    #[command(subcommand)]
    Auth(AuthCommands),
    
    /// Task management
    #[command(subcommand)]  
    Task(TaskCommands),
    
    /// Data management
    #[command(subcommand)]
    Data(DataCommands),
    
    /// Submit a task (shorthand for `task submit`)
    Submit {
        /// Path to task.toml
        #[arg(short, long, default_value = "task.toml")]
        config: String,
    },
    
    /// Show task status (shorthand for `task status`)
    Status {
        /// Task ID (optional, shows all if not provided)
        task_id: Option<String>,
    },
}

#[derive(Subcommand)]
enum AuthCommands {
    /// Register a new user
    Register {
        /// Username
        username: String,
    },
    /// Login
    Login {
        /// Username
        username: String,
    },
    /// Show current user
    Whoami,
    /// Logout
    Logout,
}

#[derive(Subcommand)]
enum TaskCommands {
    /// Submit a new task
    Submit {
        #[arg(short, long, default_value = "task.toml")]
        config: String,
    },
    /// Show task status
    Status {
        task_id: Option<String>,
    },
    /// List all tasks
    List {
        #[arg(short, long, default_value = "10")]
        limit: usize,
    },
    /// Show task logs
    Logs {
        task_id: String,
        #[arg(short, long)]
        follow: bool,
    },
    /// Cancel a task
    Cancel {
        task_id: String,
    },
}

#[derive(Subcommand)]
enum DataCommands {
    /// Pull task results
    Pull {
        task_id: String,
        #[arg(short, long)]
        output: Option<String>,
    },
    /// Pre-sync dataset to remote cache
    SyncDataset {
        path: String,
        #[arg(short, long)]
        name: Option<String>,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    
    // 初始化 tracing
    tracing_subscriber::fmt::init();
    
    // 创建 HTTP client
    let client = reqwest::Client::new();
    
    match cli.command {
        Commands::Auth(cmd) => commands::auth::handle(cmd, &client, &cli.proxy_url).await,
        Commands::Task(cmd) => commands::task::handle(cmd, &client, &cli.proxy_url).await,
        Commands::Data(cmd) => commands::data::handle(cmd, &client, &cli.proxy_url).await,
        Commands::Submit { config } => {
            commands::task::handle(
                TaskCommands::Submit { config },
                &client,
                &cli.proxy_url,
            ).await
        }
        Commands::Status { task_id } => {
            commands::task::handle(
                TaskCommands::Status { task_id },
                &client,
                &cli.proxy_url,
            ).await
        }
    }
}
```

### 5.2 Submit 命令实现

```rust
// crates/ailab-cli/src/commands/task.rs

use std::path::Path;
use indicatif::{ProgressBar, ProgressStyle};
use ailab_core::types::task::TaskConfig;

pub async fn submit(
    client: &reqwest::Client,
    proxy_url: &str,
    config_path: &str,
) -> anyhow::Result<()> {
    // 读取配置
    let config_content = std::fs::read_to_string(config_path)?;
    let task_config: TaskConfig = toml::from_str(&config_content)?;
    
    println!("📦 Preparing task: {}", task_config.name);
    
    // 获取项目目录
    let project_dir = Path::new(config_path).parent().unwrap_or(Path::new("."));
    
    // 收集文件信息
    let pb = ProgressBar::new_spinner();
    pb.set_style(ProgressStyle::default_spinner()
        .template("{spinner:.green} {msg}")?);
    pb.set_message("Collecting files...");
    
    // 读取 .ailabignore
    let ignore_path = project_dir.join(".ailabignore");
    let ignore_patterns: Vec<String> = if ignore_path.exists() {
        std::fs::read_to_string(&ignore_path)?
            .lines()
            .map(String::from)
            .collect()
    } else {
        vec![]
    };
    
    // 计算 hash
    let env_hash = ailab_core::hash::hash_environment(project_dir)?;
    let project_hash = ailab_core::hash::hash_directory(project_dir, &ignore_patterns)?;
    
    pb.finish_with_message("Files collected");
    
    // 提交到 proxy
    #[derive(serde::Serialize)]
    struct SubmitRequest {
        config: TaskConfig,
        project_dir: String,
        env_hash: String,
        project_hash: String,
        ignore_patterns: Vec<String>,
    }
    
    let request = SubmitRequest {
        config: task_config.clone(),
        project_dir: project_dir.to_string_lossy().to_string(),
        env_hash,
        project_hash,
        ignore_patterns,
    };
    
    println!("🚀 Submitting to proxy...");
    
    let response = client
        .post(format!("{}/api/tasks/submit", proxy_url))
        .json(&request)
        .send()
        .await?;
    
    if response.status().is_success() {
        #[derive(serde::Deserialize)]
        struct SubmitResponse {
            task_id: String,
            message: String,
        }
        
        let result: SubmitResponse = response.json().await?;
        println!("✅ Task submitted successfully!");
        println!("   Task ID: {}", result.task_id);
        println!("   {}", result.message);
        println!();
        println!("   Check status: ailab status {}", result.task_id);
    } else {
        let error: serde_json::Value = response.json().await?;
        println!("❌ Submission failed: {}", error);
    }
    
    Ok(())
}
```

## 6. Local Proxy Server (ailab-proxy)

### 6.1 主服务器

```rust
// crates/ailab-proxy/src/server.rs

use axum::{
    routing::{get, post},
    Router,
    Extension,
};
use std::sync::Arc;
use tower_http::trace::TraceLayer;

use crate::{
    api,
    services::{UserService, SyncService, CacheService, PollerService},
    db::Database,
    web,
};
use ailab_core::transport::Transport;
use ailab_core::storage::Storage;

pub struct AppState {
    pub db: Database,
    pub transport: Arc<dyn Transport>,
    pub storage: Arc<dyn Storage>,
    pub user_service: UserService,
    pub sync_service: SyncService,
    pub cache_service: CacheService,
}

pub async fn create_app(
    db: Database,
    transport: Arc<dyn Transport>,
    storage: Arc<dyn Storage>,
) -> Router {
    let user_service = UserService::new(db.clone());
    let cache_service = CacheService::new(db.clone(), storage.clone());
    let sync_service = SyncService::new(storage.clone(), cache_service.clone());
    
    let state = Arc::new(AppState {
        db,
        transport,
        storage,
        user_service,
        sync_service,
        cache_service,
    });
    
    // API routes
    let api_routes = Router::new()
        .route("/auth/register", post(api::auth::register))
        .route("/auth/login", post(api::auth::login))
        .route("/auth/whoami", get(api::auth::whoami))
        .route("/tasks/submit", post(api::tasks::submit))
        .route("/tasks", get(api::tasks::list))
        .route("/tasks/:id", get(api::tasks::get))
        .route("/tasks/:id/cancel", post(api::tasks::cancel))
        .route("/tasks/:id/logs", get(api::tasks::logs))
        .route("/data/pull/:task_id", get(api::data::pull))
        .route("/data/sync-dataset", post(api::data::sync_dataset));
    
    // Web UI routes
    let web_routes = Router::new()
        .route("/", get(web::handlers::dashboard))
        .route("/tasks", get(web::handlers::task_list))
        .route("/tasks/:id", get(web::handlers::task_detail))
        .route("/admin", get(web::handlers::admin_dashboard));
    
    Router::new()
        .nest("/api", api_routes)
        .nest("/web", web_routes)
        .layer(TraceLayer::new_for_http())
        .layer(Extension(state))
}
```

### 6.2 任务提交 API

```rust
// crates/ailab-proxy/src/api/tasks.rs

use axum::{
    extract::{Extension, Path, Query},
    Json,
    http::StatusCode,
};
use std::sync::Arc;
use uuid::Uuid;

use crate::server::AppState;
use ailab_core::{
    types::{task::*, message::*},
    transport::Channel,
};

#[derive(serde::Deserialize)]
pub struct SubmitRequest {
    pub config: TaskConfig,
    pub project_dir: String,
    pub env_hash: String,
    pub project_hash: String,
    pub ignore_patterns: Vec<String>,
}

#[derive(serde::Serialize)]
pub struct SubmitResponse {
    pub task_id: String,
    pub message: String,
}

pub async fn submit(
    Extension(state): Extension<Arc<AppState>>,
    Json(request): Json<SubmitRequest>,
) -> Result<Json<SubmitResponse>, (StatusCode, String)> {
    // 获取当前用户（从认证中间件）
    let user_id = "current_user".to_string();  // TODO: 从认证获取
    
    let task_id = Uuid::new_v4();
    
    // 1. 检查缓存，确定需要上传的内容
    let env_cached = state.cache_service.has_env(&request.env_hash).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let project_cached = state.cache_service.has_project(&request.project_hash).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    
    // 2. 上传未缓存的内容
    let project_path = std::path::Path::new(&request.project_dir);
    
    let storage_keys = StorageKeys {
        env: format!("envs/{}.tar.gz", request.env_hash),
        project: format!("projects/{}.tar.gz", request.project_hash),
        data: vec![],  // TODO: 处理数据文件
        whls: vec![],  // TODO: 处理 wheel 文件
    };
    
    if !env_cached {
        state.sync_service.upload_env(
            project_path,
            &storage_keys.env,
        ).await.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        
        state.cache_service.mark_env_cached(&request.env_hash, &storage_keys.env).await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    
    if !project_cached {
        state.sync_service.upload_project(
            project_path,
            &storage_keys.project,
            &request.ignore_patterns,
        ).await.map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
        
        state.cache_service.mark_project_cached(&request.project_hash, &storage_keys.project).await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    
    // 3. 创建任务记录
    let task = Task {
        id: task_id,
        user_id: user_id.clone(),
        config: request.config,
        status: TaskStatus::Pending,
        env_hash: request.env_hash,
        project_hash: request.project_hash,
        data_hashes: vec![],
        whl_hashes: vec![],
        created_at: chrono::Utc::now(),
        updated_at: chrono::Utc::now(),
        started_at: None,
        completed_at: None,
        slurm_job_id: None,
        exit_code: None,
        error_message: None,
        gpu_seconds: None,
        cpu_seconds: None,
    };
    
    state.db.insert_task(&task).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    
    // 4. 发送消息到远端
    let message = ControlMessage::new(MessagePayload::SubmitTask {
        task: task.clone(),
        storage_keys,
    });
    
    state.transport.send(Channel::ToRemote, message).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    
    Ok(Json(SubmitResponse {
        task_id: task_id.to_string(),
        message: if env_cached && project_cached {
            "Task submitted (using cached environment and project)".to_string()
        } else {
            "Task submitted (files uploaded)".to_string()
        },
    }))
}

#[derive(serde::Deserialize)]
pub struct ListQuery {
    pub limit: Option<usize>,
    pub user_id: Option<String>,
}

pub async fn list(
    Extension(state): Extension<Arc<AppState>>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Task>>, (StatusCode, String)> {
    let user_id = "current_user".to_string();  // TODO: 从认证获取
    let limit = query.limit.unwrap_or(20);
    
    let tasks = state.db.list_tasks(&user_id, limit).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    
    Ok(Json(tasks))
}

pub async fn get(
    Extension(state): Extension<Arc<AppState>>,
    Path(id): Path<String>,
) -> Result<Json<Task>, (StatusCode, String)> {
    let task_id = Uuid::parse_str(&id)
        .map_err(|_| (StatusCode::BAD_REQUEST, "Invalid task ID".to_string()))?;
    
    let task = state.db.get_task(&task_id).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or((StatusCode::NOT_FOUND, "Task not found".to_string()))?;
    
    Ok(Json(task))
}

pub async fn cancel(
    Extension(state): Extension<Arc<AppState>>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let task_id = Uuid::parse_str(&id)
        .map_err(|_| (StatusCode::BAD_REQUEST, "Invalid task ID".to_string()))?;
    let user_id = "current_user".to_string();
    
    // 发送取消消息
    let message = ControlMessage::new(MessagePayload::CancelTask {
        task_id,
        user_id,
    });
    
    state.transport.send(Channel::ToRemote, message).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    
    Ok(Json(serde_json::json!({
        "message": "Cancel request sent"
    })))
}
```

### 6.3 消息轮询服务

```rust
// crates/ailab-proxy/src/services/poller.rs

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::broadcast;
use tracing::{info, warn, error};

use ailab_core::{
    transport::{Transport, Channel},
    types::message::{ControlMessage, MessagePayload},
};
use crate::db::Database;

pub struct PollerService {
    transport: Arc<dyn Transport>,
    db: Database,
    shutdown_rx: broadcast::Receiver<()>,
}

impl PollerService {
    pub fn new(
        transport: Arc<dyn Transport>,
        db: Database,
        shutdown_rx: broadcast::Receiver<()>,
    ) -> Self {
        Self {
            transport,
            db,
            shutdown_rx,
        }
    }
    
    pub async fn run(mut self) {
        info!("Starting message poller");
        
        loop {
            tokio::select! {
                _ = self.shutdown_rx.recv() => {
                    info!("Poller shutting down");
                    break;
                }
                result = self.poll_once() => {
                    if let Err(e) = result {
                        error!("Poll error: {}", e);
                        tokio::time::sleep(Duration::from_secs(5)).await;
                    }
                }
            }
        }
    }
    
    async fn poll_once(&self) -> anyhow::Result<()> {
        let message = self.transport
            .receive(Channel::ToLocal, Duration::from_secs(10))
            .await?;
        
        if let Some(msg) = message {
            self.handle_message(&msg).await?;
            self.transport.ack(Channel::ToLocal, &msg.id).await?;
        }
        
        Ok(())
    }
    
    async fn handle_message(&self, message: &ControlMessage) -> anyhow::Result<()> {
        match &message.payload {
            MessagePayload::StatusUpdate {
                task_id,
                status,
                slurm_job_id,
                progress,
                error_message,
            } => {
                info!("Task {} status: {:?}", task_id, status);
                
                self.db.update_task_status(
                    task_id,
                    *status,
                    slurm_job_id.clone(),
                    error_message.clone(),
                ).await?;
            }
            
            MessagePayload::TaskCompleted {
                task_id,
                status,
                exit_code,
                result_keys,
                gpu_seconds,
                cpu_seconds,
                error_message,
            } => {
                info!("Task {} completed: {:?}", task_id, status);
                
                self.db.complete_task(
                    task_id,
                    *status,
                    *exit_code,
                    *gpu_seconds,
                    *cpu_seconds,
                    result_keys.clone(),
                    error_message.clone(),
                ).await?;
            }
            
            MessagePayload::Heartbeat { source, timestamp } => {
                info!("Heartbeat from {} at {}", source, timestamp);
            }
            
            _ => {
                warn!("Unexpected message type: {:?}", message.payload);
            }
        }
        
        Ok(())
    }
}
```

## 7. Remote Server (ailab-remote)

### 7.1 主服务器循环

```rust
// crates/ailab-remote/src/server.rs

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::broadcast;
use tracing::{info, warn, error};

use ailab_core::{
    transport::{Transport, Channel},
    storage::Storage,
    types::message::{ControlMessage, MessagePayload},
};
use crate::{
    services::{TaskProcessor, SlurmMonitor, Accounting},
    db::Database,
};

pub struct RemoteServer {
    transport: Arc<dyn Transport>,
    storage: Arc<dyn Storage>,
    db: Database,
    processor: TaskProcessor,
    monitor: SlurmMonitor,
    accounting: Accounting,
}

impl RemoteServer {
    pub async fn new(
        transport: Arc<dyn Transport>,
        storage: Arc<dyn Storage>,
        db: Database,
        config: &crate::Config,
    ) -> anyhow::Result<Self> {
        let processor = TaskProcessor::new(
            storage.clone(),
            config.paths.clone(),
        );
        let monitor = SlurmMonitor::new();
        let accounting = Accounting::new(db.clone());
        
        Ok(Self {
            transport,
            storage,
            db,
            processor,
            monitor,
            accounting,
        })
    }
    
    pub async fn run(self, mut shutdown_rx: broadcast::Receiver<()>) {
        info!("Remote server starting");
        
        // 启动 Slurm 监控任务
        let monitor = self.monitor.clone();
        let transport = self.transport.clone();
        let db = self.db.clone();
        let accounting = self.accounting.clone();
        
        let monitor_handle = tokio::spawn(async move {
            Self::run_monitor(monitor, transport, db, accounting).await;
        });
        
        // 主消息处理循环
        loop {
            tokio::select! {
                _ = shutdown_rx.recv() => {
                    info!("Server shutting down");
                    break;
                }
                result = self.poll_and_process() => {
                    if let Err(e) = result {
                        error!("Processing error: {}", e);
                        tokio::time::sleep(Duration::from_secs(5)).await;
                    }
                }
            }
        }
        
        monitor_handle.abort();
    }
    
    async fn poll_and_process(&self) -> anyhow::Result<()> {
        let message = self.transport
            .receive(Channel::ToRemote, Duration::from_secs(5))
            .await?;
        
        if let Some(msg) = message {
            self.handle_message(&msg).await?;
            self.transport.ack(Channel::ToRemote, &msg.id).await?;
        }
        
        Ok(())
    }
    
    async fn handle_message(&self, message: &ControlMessage) -> anyhow::Result<()> {
        match &message.payload {
            MessagePayload::SubmitTask { task, storage_keys } => {
                info!("Processing task submission: {}", task.id);
                
                // 更新状态为 Preparing
                self.send_status_update(&task.id, TaskStatus::Preparing, None, None).await?;
                
                // 处理任务
                match self.processor.process(task, storage_keys).await {
                    Ok(slurm_job_id) => {
                        // 记录任务
                        self.db.insert_task(task, &slurm_job_id).await?;
                        
                        // 更新状态为 Queued
                        self.send_status_update(
                            &task.id,
                            TaskStatus::Queued,
                            Some(slurm_job_id),
                            None,
                        ).await?;
                    }
                    Err(e) => {
                        error!("Task processing failed: {}", e);
                        self.send_status_update(
                            &task.id,
                            TaskStatus::Failed,
                            None,
                            Some(e.to_string()),
                        ).await?;
                    }
                }
            }
            
            MessagePayload::CancelTask { task_id, user_id } => {
                info!("Cancelling task: {}", task_id);
                
                if let Some(job_id) = self.db.get_slurm_job_id(task_id).await? {
                    self.monitor.cancel_job(&job_id).await?;
                }
            }
            
            MessagePayload::QueryStatus { task_ids } => {
                let statuses = self.db.get_task_statuses(task_ids).await?;
                
                let response = ControlMessage::new(MessagePayload::StatusResponse {
                    tasks: statuses,
                });
                
                self.transport.send(Channel::ToLocal, response).await?;
            }
            
            _ => {
                warn!("Unexpected message type");
            }
        }
        
        Ok(())
    }
    
    async fn send_status_update(
        &self,
        task_id: &TaskId,
        status: TaskStatus,
        slurm_job_id: Option<String>,
        error_message: Option<String>,
    ) -> anyhow::Result<()> {
        let message = ControlMessage::new(MessagePayload::StatusUpdate {
            task_id: *task_id,
            status,
            slurm_job_id,
            progress: None,
            error_message,
        });
        
        self.transport.send(Channel::ToLocal, message).await?;
        Ok(())
    }
    
    async fn run_monitor(
        monitor: SlurmMonitor,
        transport: Arc<dyn Transport>,
        db: Database,
        accounting: Accounting,
    ) {
        let mut interval = tokio::time::interval(Duration::from_secs(30));
        
        loop {
            interval.tick().await;
            
            // 获取所有运行中的任务
            let running_tasks = match db.get_running_tasks().await {
                Ok(tasks) => tasks,
                Err(e) => {
                    error!("Failed to get running tasks: {}", e);
                    continue;
                }
            };
            
            for (task_id, slurm_job_id) in running_tasks {
                match monitor.check_job_status(&slurm_job_id).await {
                    Ok(status) => {
                        if status.is_terminal() {
                            // 任务结束，处理结果
                            // ... 上传结果、更新统计等
                        }
                    }
                    Err(e) => {
                        error!("Failed to check job {}: {}", slurm_job_id, e);
                    }
                }
            }
        }
    }
}
```

### 7.2 任务处理器

```rust
// crates/ailab-remote/src/services/processor.rs

use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::process::Command;
use tracing::info;

use ailab_core::{
    storage::Storage,
    types::{task::Task, message::StorageKeys},
};

#[derive(Clone)]
pub struct PathConfig {
    pub envs_dir: PathBuf,
    pub tasks_dir: PathBuf,
    pub cache_dir: PathBuf,
}

pub struct TaskProcessor {
    storage: Arc<dyn Storage>,
    paths: PathConfig,
}

impl TaskProcessor {
    pub fn new(storage: Arc<dyn Storage>, paths: PathConfig) -> Self {
        Self { storage, paths }
    }
    
    pub async fn process(
        &self,
        task: &Task,
        storage_keys: &StorageKeys,
    ) -> anyhow::Result<String> {
        let task_dir = self.paths.tasks_dir.join(task.id.to_string());
        std::fs::create_dir_all(&task_dir)?;
        
        // 1. 准备环境
        let env_dir = self.ensure_environment(&task.env_hash, &storage_keys.env).await?;
        
        // 2. 下载项目
        let project_dir = task_dir.join("project");
        self.storage.download_dir(&storage_keys.project, &project_dir).await?;
        
        // 3. 下载数据（如果有）
        for data_key in &storage_keys.data {
            let data_name = data_key.split('/').last().unwrap_or("data");
            let data_dir = task_dir.join("data").join(data_name);
            self.storage.download_dir(data_key, &data_dir).await?;
        }
        
        // 4. 安装额外的 wheels
        for whl_key in &storage_keys.whls {
            let whl_path = task_dir.join("whls").join(
                whl_key.split('/').last().unwrap_or("package.whl")
            );
            self.storage.download(whl_key, &whl_path).await?;
            
            self.install_wheel(&env_dir, &whl_path).await?;
        }
        
        // 5. 生成 Slurm 脚本
        let script_path = self.generate_slurm_script(task, &task_dir, &env_dir, &project_dir)?;
        
        // 6. 提交到 Slurm
        let job_id = self.submit_to_slurm(&script_path).await?;
        
        Ok(job_id)
    }
    
    async fn ensure_environment(
        &self,
        env_hash: &str,
        storage_key: &str,
    ) -> anyhow::Result<PathBuf> {
        let env_dir = self.paths.envs_dir.join(env_hash);
        
        if env_dir.exists() {
            info!("Using cached environment: {}", env_hash);
            return Ok(env_dir);
        }
        
        info!("Building environment: {}", env_hash);
        
        // 下载环境文件
        let env_files_dir = self.paths.cache_dir.join("env_files").join(env_hash);
        self.storage.download_dir(storage_key, &env_files_dir).await?;
        
        // 创建虚拟环境
        let venv_dir = env_dir.join(".venv");
        Command::new("uv")
            .args(["venv", venv_dir.to_str().unwrap()])
            .current_dir(&env_files_dir)
            .status()
            .await?;
        
        // 安装依赖
        Command::new("uv")
            .args(["sync", "--frozen"])
            .current_dir(&env_files_dir)
            .env("VIRTUAL_ENV", &venv_dir)
            .status()
            .await?;
        
        Ok(env_dir)
    }
    
    async fn install_wheel(&self, env_dir: &Path, whl_path: &Path) -> anyhow::Result<()> {
        let venv_dir = env_dir.join(".venv");
        
        Command::new("uv")
            .args(["pip", "install", whl_path.to_str().unwrap()])
            .env("VIRTUAL_ENV", &venv_dir)
            .status()
            .await?;
        
        Ok(())
    }
    
    fn generate_slurm_script(
        &self,
        task: &Task,
        task_dir: &Path,
        env_dir: &Path,
        project_dir: &Path,
    ) -> anyhow::Result<PathBuf> {
        let script_path = task_dir.join("job.sh");
        let venv_activate = env_dir.join(".venv/bin/activate");
        
        let workdir = if task.config.run.workdir == "." {
            project_dir.to_path_buf()
        } else {
            project_dir.join(&task.config.run.workdir)
        };
        
        let command = task.config.run.command.clone()
            .or_else(|| task.config.run.script.as_ref().map(|s| format!("bash {}", s)))
            .unwrap_or_else(|| "echo 'No command specified'".to_string());
        
        let script = format!(r#"#!/bin/bash
#SBATCH --job-name=ailab-{task_id}
#SBATCH --gres=gpu:{gpus}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output={task_dir}/slurm_%j.out
#SBATCH --error={task_dir}/slurm_%j.err

set -e

# Activate environment
source {venv_activate}

# Enter working directory
cd {workdir}

# Run command
{command}

# Save exit code
echo $? > {task_dir}/exit_code
"#,
            task_id = task.id,
            gpus = task.config.resources.gpus,
            cpus = task.config.resources.cpus,
            memory = task.config.resources.memory,
            time_limit = task.config.resources.time_limit,
            task_dir = task_dir.display(),
            venv_activate = venv_activate.display(),
            workdir = workdir.display(),
            command = command,
        );
        
        std::fs::write(&script_path, script)?;
        
        Ok(script_path)
    }
    
    async fn submit_to_slurm(&self, script_path: &Path) -> anyhow::Result<String> {
        let output = Command::new("sbatch")
            .arg(script_path)
            .output()
            .await?;
        
        if !output.status.success() {
            anyhow::bail!(
                "sbatch failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }
        
        // 解析输出获取 job ID
        // 格式: "Submitted batch job 12345"
        let stdout = String::from_utf8_lossy(&output.stdout);
        let job_id = stdout
            .split_whitespace()
            .last()
            .ok_or_else(|| anyhow::anyhow!("Failed to parse job ID"))?
            .to_string();
        
        Ok(job_id)
    }
}
```

## 8. 配置文件

### 8.1 Proxy 配置

```toml
# config/proxy.toml

[server]
host = "0.0.0.0"
port = 8800

# 控制面传输配置
[transport]
type = "s3"
endpoint = "http://minio.internal:9000"
bucket = "ailab-course"
access_key = "minioadmin"
secret_key = "minioadmin"
prefix = "messages"
poll_interval_ms = 5000

# 或者使用 Redis
# [transport]
# type = "redis"
# url = "redis://redis.internal:6379"
# prefix = "ailab"

# 数据面存储配置
[storage]
type = "s3"
endpoint = "http://minio.internal:9000"
bucket = "ailab-course"
access_key = "minioadmin"
secret_key = "minioadmin"

[database]
path = "/var/lib/ailab-proxy/data.db"

[cache]
max_size_gb = 100
cleanup_threshold_percent = 90
```

### 8.2 Remote 配置

```toml
# config/remote.toml

[transport]
type = "s3"
endpoint = "http://minio.internal:9000"
bucket = "ailab-course"
access_key = "minioadmin"
secret_key = "minioadmin"
prefix = "messages"
poll_interval_ms = 3000

[storage]
type = "s3"
endpoint = "http://minio.internal:9000"
bucket = "ailab-course"
access_key = "minioadmin"
secret_key = "minioadmin"

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

## 9. 存储结构

```
bucket: ailab-course/
├── messages/                    # 控制面消息
│   ├── to_remote/              # Local → Remote
│   │   └── {msg_id}.json
│   ├── to_local/               # Remote → Local
│   │   └── {msg_id}.json
│   └── processed/              # 已处理的消息归档
│       └── {date}/{msg_id}.json
│
├── envs/                        # 环境文件
│   └── {env_hash}.tar.gz       # 包含 uv.lock, pyproject.toml
│
├── projects/                    # 项目代码
│   └── {project_hash}.tar.gz
│
├── datasets/                    # 数据集
│   └── {dataset_hash}/
│
├── whls/                        # 自定义 wheel
│   └── {whl_hash}.whl
│
└── results/                     # 任务结果
    └── {task_id}/
        ├── outputs/
        ├── logs/
        └── metadata.json
```

## 10. 实现路线图

### Phase 1: 核心功能 (3-4 天)

1. **ailab-core**: 类型定义、trait 定义、hash 工具
2. **ailab-transport**: S3 Transport 实现
3. **ailab-storage**: S3 Storage 实现
4. **ailab-cli**: 基础命令 (submit, status, list)
5. **ailab-proxy**: HTTP API、基础任务管理、消息轮询
6. **ailab-remote**: 消息处理、环境构建、Slurm 提交

### Phase 2: 完善功能 (2-3 天)

1. **ailab-cli**: logs, cancel, pull 命令
2. **ailab-proxy**: 用户认证、缓存管理
3. **ailab-remote**: 任务监控、结果上传、统计
4. **ailab-transport**: Redis Transport 实现

### Phase 3: Web UI 和优化 (2 天)

1. **ailab-proxy**: Web 状态页面
2. 错误处理完善
3. 重试机制
4. 文档

## 11. 关键设计决策总结

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Transport 抽象 | Trait + 多实现 | 灵活支持不同后端，便于测试 |
| Control/Data 分离 | 消息用 Transport，文件用 Storage | 大文件始终走对象存储，消息可灵活选择 |
| 消息格式 | JSON + 类型标签 | 可读性好，调试方便 |
| 环境管理 | uv + 基于 hash 的缓存 | 简单可靠，避免重复构建 |
| 数据库 | SQLite | 轻量，单机足够，无需额外部署 |
| Web 框架 | Axum | 现代、类型安全、性能好 |
| CLI 框架 | Clap derive | 类型安全，自动生成帮助 |

