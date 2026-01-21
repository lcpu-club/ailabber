"""Local Slurm Service - 本地Slurm作业管理服务"""
from pathlib import Path
from typing import Tuple
from sqlalchemy.orm import Session

from core.database import TaskModel
from utils.logger import get_logger
from utils.slurm import (
    generate_slurm_script,
    submit_slurm_job,
    get_slurm_job_status,
    cancel_slurm_job,
    map_slurm_state,
)

logger = get_logger("local_slurm_service")


class LocalSlurmService:
    """本地Slurm作业管理服务"""
    
    @staticmethod
    def submit_job(
        task: TaskModel,
        data: dict
    ) -> Tuple[bool, str, str]:
        """
        提交本地Slurm作业
        
        Args:
            task: 任务对象
            data: 任务数据
            
        Returns:
            (success, job_id/error, message)
        """
        try:
            username = data['username']
            task_id = task.task_id
            
            # 确定工作目录
            upload_path = Path(data.get('upload', '.'))
            workdir = data.get('workdir', '.')
            
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = upload_path / workdir if upload_path.exists() else Path(workdir)
            
            work_path = work_path.resolve()
            work_path.mkdir(parents=True, exist_ok=True)
            
            # Slurm 输出目录
            slurm_dir = work_path / ".slurm"
            slurm_dir.mkdir(exist_ok=True)
            
            output_file = str(slurm_dir / f"{task_id}.out")
            error_file = str(slurm_dir / f"{task_id}.err")
            script_file = str(slurm_dir / f"{task_id}.sh")
            
            # 解析命令
            commands = data.get('commands', [])
            if isinstance(commands, str):
                commands = commands.split(' && ')
            
            # 生成 Slurm 脚本
            script_content = generate_slurm_script(
                task_id=task_id,
                username=username,
                workdir=str(work_path),
                commands=commands,
                gpus=data.get('gpus', 0),
                cpus=data.get('cpus', 1),
                memory=data.get('memory', '4G'),
                time_limit=data.get('time_limit', '1:00:00'),
                output_file=output_file,
                error_file=error_file,
                partition=data.get('partition')
            )
            
            # 写入脚本
            with open(script_file, 'w') as f:
                f.write(script_content)
            
            logger.info(f"生成本地 Slurm 脚本: {script_file}")
            
            # 提交作业
            success, result, stdout = submit_slurm_job(script_file)
            
            if success:
                logger.info(f"本地 Slurm 作业提交成功: task={task_id}, job={result}")
                return True, result, f"本地 Slurm 作业提交成功: {result}"
            else:
                logger.error(f"本地 Slurm 提交失败: task={task_id}, error={result}")
                return False, result, f"本地 Slurm 提交失败: {result}"
                
        except Exception as e:
            logger.error(f"本地任务提交异常: {task.task_id} - {e}")
            return False, str(e), f"本地任务提交失败: {e}"
    
    @staticmethod
    def get_job_status(job_id: str):
        """获取本地Slurm作业状态"""
        return get_slurm_job_status(job_id)
    
    @staticmethod
    def cancel_job(job_id: str) -> Tuple[bool, str]:
        """取消本地Slurm作业"""
        return cancel_slurm_job(job_id)
    
    @staticmethod
    def map_job_state(slurm_state: str) -> str:
        """映射Slurm状态到统一状态"""
        return map_slurm_state(slurm_state)
