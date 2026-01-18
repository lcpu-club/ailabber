"""
数据库 ORM 模型

使用 SQLAlchemy 定义数据库模型
"""
from datetime import datetime
from typing import Optional
import hashlib
import uuid

from sqlalchemy import create_engine, String, Integer, Float, Text, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

from shared.config import LOCAL_DB_PATH, REMOTE_DB_PATH, DATA_DIR


# ============ Base ============

class Base(DeclarativeBase):
    """ORM 基类"""
    pass


# ============ Local Proxy 模型 ============

class UserModel(Base):
    """用户表"""
    __tablename__ = "users"
    
    pubkey_fingerprint: Mapped[str] = mapped_column(String(32), primary_key=True)
    pubkey: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    total_gpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_cpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    
    def to_dict(self) -> dict:
        return {
            "pubkey_fingerprint": self.pubkey_fingerprint,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_tasks": self.total_tasks,
            "total_gpu_hours": self.total_gpu_hours,
            "total_cpu_hours": self.total_cpu_hours,
        }


class TaskModel(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    task_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    command: Mapped[Optional[str]] = mapped_column(Text)
    gpus: Mapped[int] = mapped_column(Integer, default=1)
    cpus: Mapped[int] = mapped_column(Integer, default=4)
    memory: Mapped[str] = mapped_column(String(16), default="8G")
    time_limit: Mapped[str] = mapped_column(String(16), default="1:00:00")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    logs: Mapped[Optional[str]] = mapped_column(Text)
    project_hash: Mapped[Optional[str]] = mapped_column(String(64))
    env_hash: Mapped[Optional[str]] = mapped_column(String(64))
    slurm_job_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    @staticmethod
    def generate_id() -> str:
        """生成任务 ID"""
        return str(uuid.uuid4())[:8]
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "username": self.username,
            "name": self.name,
            "status": self.status,
            "command": self.command,
            "gpus": self.gpus,
            "cpus": self.cpus,
            "memory": self.memory,
            "time_limit": self.time_limit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "exit_code": self.exit_code,
            "slurm_job_id": self.slurm_job_id,
        }



class MessageLogModel(Base):
    """消息日志表"""
    __tablename__ = "message_log"
    
    msg_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    msg_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # outgoing, incoming
    payload: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# ============ Remote Server 模型 ============

class TaskExecutionModel(Base):
    """任务执行记录表 (Remote)"""
    __tablename__ = "task_executions"
    
    task_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    command: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    slurm_job_id: Mapped[Optional[str]] = mapped_column(String(32))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    stdout: Mapped[Optional[str]] = mapped_column(Text)
    stderr: Mapped[Optional[str]] = mapped_column(Text)
    gpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    cpu_hours: Mapped[float] = mapped_column(Float, default=0.0)


class UserStatsModel(Base):
    """用户统计表 (Remote)"""
    __tablename__ = "user_stats"
    
    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    successful_tasks: Mapped[int] = mapped_column(Integer, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    total_gpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_cpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    last_task_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# ============ 数据库引擎管理 ============

# Local Proxy 使用的模型
LOCAL_MODELS = [UserModel, TaskModel, CacheManifestModel, MessageLogModel]

# Remote Server 使用的模型
REMOTE_MODELS = [TaskExecutionModel, UserStatsModel, EnvCacheModel]


def get_local_engine():
    """获取 Local Proxy 数据库引擎"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{LOCAL_DB_PATH}", echo=False)


def get_remote_engine():
    """获取 Remote Server 数据库引擎"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{REMOTE_DB_PATH}", echo=False)


def init_local_db():
    """初始化 Local Proxy 数据库"""
    engine = get_local_engine()
    # 只创建 Local 相关的表
    UserModel.__table__.create(engine, checkfirst=True)
    TaskModel.__table__.create(engine, checkfirst=True)
    CacheManifestModel.__table__.create(engine, checkfirst=True)
    MessageLogModel.__table__.create(engine, checkfirst=True)
    return engine


def init_remote_db():
    """初始化 Remote Server 数据库"""
    engine = get_remote_engine()
    # 只创建 Remote 相关的表
    TaskExecutionModel.__table__.create(engine, checkfirst=True)
    UserStatsModel.__table__.create(engine, checkfirst=True)
    EnvCacheModel.__table__.create(engine, checkfirst=True)
    return engine


def get_local_session() -> Session:
    """获取 Local Proxy 数据库会话"""
    engine = get_local_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def get_remote_session() -> Session:
    """获取 Remote Server 数据库会话"""
    engine = get_remote_engine()
    SessionRemote = sessionmaker(bind=engine)
    return SessionRemote()
