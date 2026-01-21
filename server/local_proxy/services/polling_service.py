"""Polling Service - 任务状态轮询服务"""
import threading
import time
from datetime import datetime

from core.database import get_local_session, TaskModel
from core.config import POLL_INTERVAL
from utils.logger import get_logger
from .local_slurm_service import LocalSlurmService
from .remote_slurm_service import RemoteSlurmService
from .task_service import TaskService

logger = get_logger("polling_service")


class PollingService:
    """任务状态轮询服务"""
    
    def __init__(self):
        self.polling_thread = None
        self.stop_event = threading.Event()
    
    def start(self):
        """启动轮询线程"""
        if self.polling_thread is None or not self.polling_thread.is_alive():
            self.stop_event.clear()
            self.polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.polling_thread.start()
            logger.info("启动任务状态轮询线程")
    
    def stop(self):
        """停止轮询线程"""
        self.stop_event.set()
        if self.polling_thread:
            self.polling_thread.join(timeout=5)
            logger.info("任务状态轮询线程已停止")
    
    def is_running(self) -> bool:
        """检查轮询线程是否运行中"""
        return self.polling_thread is not None and self.polling_thread.is_alive()
    
    def _poll_loop(self):
        """轮询循环"""
        logger.info("任务状态轮询线程已启动")
        
        while not self.stop_event.is_set():
            try:
                session = get_local_session()
                
                # 查询运行中的任务
                running_tasks = session.query(TaskModel).filter(
                    TaskModel.status.in_(['running', 'pending'])
                ).all()
                
                for task in running_tasks:
                    if not task.slurm_job_id:
                        continue
                    
                    try:
                        if task.target in ['local', 'local-run']:
                            # 本地 Slurm 状态查询
                            self._poll_local_task(session, task)
                        
                        elif task.target == 'remote':
                            # 远程 Slurm 状态查询
                            self._poll_remote_task(session, task)
                    
                    except Exception as e:
                        logger.error(f"轮询任务 {task.task_id} 失败: {e}")
                
                session.close()
                
            except Exception as e:
                logger.error(f"轮询循环异常: {e}")
            
            # 等待下一次轮询
            self.stop_event.wait(POLL_INTERVAL)
        
        logger.info("任务状态轮询线程已退出")
    
    def _poll_local_task(self, session, task: TaskModel):
        """轮询本地任务状态"""
        job_info = LocalSlurmService.get_job_status(task.slurm_job_id)
        if job_info:
            new_status = LocalSlurmService.map_job_state(job_info.state)
            if new_status != task.status:
                # 更新任务状态
                TaskService.update_task_status(
                    session,
                    task,
                    new_status,
                    exit_code=job_info.exit_code
                )
    
    def _poll_remote_task(self, session, task: TaskModel):
        """轮询远程任务状态"""
        status_data = RemoteSlurmService.get_job_status(task.slurm_job_id)
        if status_data:
            new_status = status_data.get('status', task.status)
            if new_status != task.status:
                # 更新任务状态
                TaskService.update_task_status(
                    session,
                    task,
                    new_status,
                    exit_code=status_data.get('exit_code')
                )


# 全局轮询服务实例
_polling_service = PollingService()


def get_polling_service() -> PollingService:
    """获取全局轮询服务实例"""
    return _polling_service
