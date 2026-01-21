"""Task Service - 任务管理服务"""
import json
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session

from core.database import TaskModel, UserModel, MessageLogModel
from utils.logger import get_logger

logger = get_logger("task_service")


class TaskService:
    """任务管理服务"""
    
    @staticmethod
    def create_task(
        session: Session,
        username: str,
        target: str,
        commands: list,
        upload: str = '.',
        ignore: list = [],
        workdir: str = '.',
        logs_path: list = [],
        results_path: list = [],
        gpus: int = 0,
        cpus: int = 1,
        memory: str = '4G',
        time_limit: str = '1:00:00',
    ) -> TaskModel:
        """
        创建任务记录
        
        Args:
            session: 数据库会话
            username: 用户名
            target: 目标（local, remote, local-run）
            commands: 执行命令列表
            其他参数: 任务配置
            
        Returns:
            TaskModel: 创建的任务对象
        """
        # 合并命令
        command_str = ' && '.join(commands) if isinstance(commands, list) else commands
        
        # 创建任务
        task = TaskModel(
            username=username,
            status="pending",
            target=target,
            upload=upload,
            ignore=json.dumps(ignore or [], ensure_ascii=False),
            commands=command_str,
            workdir=workdir,
            logs_path=json.dumps(logs_path or [], ensure_ascii=False),
            results_path=json.dumps(results_path or [], ensure_ascii=False),
            gpus=gpus,
            cpus=cpus,
            memory=memory,
            time_limit=time_limit,
        )
        session.add(task)
        
        # 更新用户统计
        user = session.query(UserModel).filter_by(username=username).first()
        if user:
            user.total_tasks += 1
        
        # 记录消息日志
        msg_log = MessageLogModel(
            msg_type="task_submit",
            direction="outgoing",
            payload=json.dumps({
                "task_id": task.task_id,
                "username": username,
                "target": target,
                "commands": commands
            }),
            created_at=datetime.now()
        )
        session.add(msg_log)
        session.commit()
        
        logger.info(f"{username} - 任务已创建: {task.task_id}, target={target}")
        return task
    
    @staticmethod
    def get_task(session: Session, task_id: str) -> Optional[TaskModel]:
        """获取任务"""
        return session.query(TaskModel).filter_by(task_id=task_id).first()
    
    @staticmethod
    def list_tasks(
        session: Session,
        username: str,
        status: Optional[str] = None
    ) -> List[TaskModel]:
        """列出用户任务"""
        query = session.query(TaskModel).filter_by(username=username)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(TaskModel.created_at.desc()).all()
    
    @staticmethod
    def update_task_status(
        session: Session,
        task: TaskModel,
        status: str,
        slurm_job_id: Optional[str] = None,
        exit_code: Optional[int] = None,
    ):
        """更新任务状态"""
        try:
            task.status = status
            if slurm_job_id:
                task.slurm_job_id = slurm_job_id
            
            if status == "running" and not task.started_at:
                task.started_at = datetime.now()
            
            if status in ['completed', 'failed', 'canceled']:
                task.completed_at = datetime.now()
                if exit_code is not None:
                    task.exit_code = exit_code
            
            task.updated_at = datetime.now()
            session.commit()
            logger.info(f"任务状态更新: {task.task_id} -> {status}")
        except Exception as e:
            session.rollback()
            logger.error(f"更新任务失败: {task.task_id} - {e}")
            raise
    
    @staticmethod
    def cancel_task(session: Session, task: TaskModel):
        """取消任务"""
        old_status = task.status
        task.status = 'canceled'
        task.completed_at = datetime.now()
        task.updated_at = datetime.now()
        
        # 记录日志
        msg_log = MessageLogModel(
            msg_type="task_cancel",
            direction="outgoing",
            payload=json.dumps({
                "task_id": task.task_id,
                "old_status": old_status,
                "new_status": "canceled"
            }),
            created_at=datetime.now()
        )
        session.add(msg_log)
        session.commit()
        
        logger.info(f"任务已取消: {task.task_id}")
