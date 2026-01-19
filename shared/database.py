"""
数据库 ORM 模型

使用 SQLAlchemy 定义数据库模型
"""
from datetime import datetime
from typing import Optional
import uuid
import shortuuid

from sqlalchemy import create_engine, String, Integer, Float, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

from shared.config import LOCAL_DB_PATH, DATA_DIR


# ============ Base ============

def generate_uuid():
    """生成完整 UUID"""
    return str(shortuuid.encode(uuid.uuid4()))

class Base(DeclarativeBase):
    """ORM 基类，统一提供创建/更新时间戳"""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.now)


# ============ Local Proxy 模型 ============

class UserModel(Base):
    """用户表"""
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    total_gpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_cpu_hours: Mapped[float] = mapped_column(Float, default=0.0)
    
    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "total_tasks": self.total_tasks,
            "total_gpu_hours": self.total_gpu_hours,
            "total_cpu_hours": self.total_cpu_hours,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TaskModel(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    task_id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    target: Mapped[str] = mapped_column(String(16), default="local", index=True)
    upload: Mapped[Optional[str]] = mapped_column(Text)  # 上传目录路径
    ignore: Mapped[Optional[str]] = mapped_column(Text)   # 忽略的文件/目录列表 (JSON)
    commands: Mapped[Optional[str]] = mapped_column(Text) # 执行命令 (合并后的字符串)
    workdir: Mapped[str] = mapped_column(String(256), default=".")
    logs_path: Mapped[Optional[str]] = mapped_column(Text)   # JSON 列表字符串
    results_path: Mapped[Optional[str]] = mapped_column(Text)  # JSON 列表字符串
    gpus: Mapped[int] = mapped_column(Integer)
    cpus: Mapped[int] = mapped_column(Integer)
    memory: Mapped[str] = mapped_column(String(16))
    time_limit: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    logs: Mapped[Optional[str]] = mapped_column(Text)  # TODO:任务执行日志
    slurm_job_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "username": self.username,
            "status": self.status,
            "target": self.target,
            "commands": self.commands,
            "workdir": self.workdir,
            "logs_path": self.logs_path,
            "results_path": self.results_path,
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
    
    msg_id: Mapped[str] = mapped_column(String(16), primary_key=True, default=generate_uuid)
    msg_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # outgoing, incoming
    payload: Mapped[Optional[str]] = mapped_column(Text)


# ============ 数据库引擎管理 ============
def get_local_engine():
    """获取 Local Proxy 数据库引擎"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{LOCAL_DB_PATH}", echo=False)


def init_local_db():
    """初始化 Local Proxy 数据库"""
    engine = get_local_engine()
    UserModel.__table__.create(engine, checkfirst=True)
    TaskModel.__table__.create(engine, checkfirst=True)
    MessageLogModel.__table__.create(engine, checkfirst=True)
    return engine


def get_local_session() -> Session:
    """获取 Local Proxy 数据库会话"""
    engine = get_local_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
