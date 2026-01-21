"""Remote Slurm Service - 远程Slurm作业管理服务"""
from typing import Tuple, Optional
import requests

from core.database import TaskModel
from core.config import REMOTE_SERVER_URL
from utils.logger import get_logger

logger = get_logger("remote_slurm_service")


class RemoteSlurmService:
    """远程Slurm作业管理服务"""
    
    @staticmethod
    def submit_job(
        task: TaskModel,
        data: dict
    ) -> Tuple[bool, str, str]:
        """
        提交远程Slurm作业
        
        Args:
            task: 任务对象
            data: 任务数据
            
        Returns:
            (success, job_id/error, message)
        """
        try:
            username = data['username']
            task_id = task.task_id
            
            # 解析命令
            commands = data.get('commands', [])
            if isinstance(commands, str):
                commands = commands.split(' && ')
            
            # 构建远程API请求数据
            remote_data = {
                "task_id": task_id,
                "username": username,
                "workdir": data.get('workdir', '.'),
                "commands": commands,
                "gpus": data.get('gpus', 0),
                "cpus": data.get('cpus', 1),
                "memory": data.get('memory', '4G'),
                "time_limit": data.get('time_limit', '1:00:00'),
                "partition": data.get('partition')
            }
            
            # 调用远程API
            resp = requests.post(
                f"{REMOTE_SERVER_URL}/api/submit",
                json=remote_data,
                timeout=30
            )
            
            if resp.status_code == 200:
                result = resp.json()
                slurm_job_id = result.get('slurm_job_id')
                logger.info(f"远程 Slurm 作业提交成功: task={task_id}, job={slurm_job_id}")
                return True, slurm_job_id, f"远程 Slurm 作业提交成功: {slurm_job_id}"
            else:
                error_msg = resp.json().get('message', '远程提交失败')
                logger.error(f"远程 Slurm 提交失败: task={task_id}, error={error_msg}")
                return False, error_msg, f"远程 Slurm 提交失败: {error_msg}"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"远程服务器连接失败: {e}")
            return False, str(e), f"无法连接远程服务器: {e}"
        except Exception as e:
            logger.error(f"远程任务提交异常: {task.task_id} - {e}")
            return False, str(e), f"远程任务提交失败: {e}"
    
    @staticmethod
    def get_job_status(job_id: str) -> Optional[dict]:
        """
        获取远程Slurm作业状态
        
        Args:
            job_id: Slurm作业ID
            
        Returns:
            作业状态信息字典或None
        """
        try:
            resp = requests.get(
                f"{REMOTE_SERVER_URL}/api/status/{job_id}",
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"查询远程作业状态失败: {job_id}")
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"查询远程任务状态失败: {job_id} - {e}")
            return None
    
    @staticmethod
    def cancel_job(job_id: str) -> Tuple[bool, str]:
        """
        取消远程Slurm作业
        
        Args:
            job_id: Slurm作业ID
            
        Returns:
            (success, message)
        """
        try:
            resp = requests.post(
                f"{REMOTE_SERVER_URL}/api/cancel/{job_id}",
                timeout=10
            )
            if resp.status_code == 200:
                return True, f"远程作业 {job_id} 已取消"
            else:
                error_msg = resp.json().get('message', '取消失败')
                logger.warning(f"取消远程 Slurm 作业失败: {error_msg}")
                return False, error_msg
        except Exception as e:
            logger.warning(f"取消远程作业异常: {e}")
            return False, str(e)
    
    @staticmethod
    def get_logs(task_id: str, username: str, workdir: str = '.') -> Optional[dict]:
        """
        获取远程任务日志
        
        Args:
            task_id: 任务ID
            username: 用户名
            workdir: 工作目录
            
        Returns:
            日志信息字典或None
        """
        try:
            resp = requests.get(
                f"{REMOTE_SERVER_URL}/api/logs/{task_id}",
                params={
                    "username": username,
                    "workdir": workdir
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"获取远程日志失败: {task_id}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"获取远程日志异常: {e}")
            return None
