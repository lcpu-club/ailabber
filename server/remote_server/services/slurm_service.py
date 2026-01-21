"""Slurm Service - Slurm作业管理服务"""
from pathlib import Path
from typing import Tuple, Optional

from core.config import REMOTE_BASE_DIR
from utils.logger import get_logger
from utils.slurm import (
    generate_slurm_script,
    submit_slurm_job,
    get_slurm_job_status,
    cancel_slurm_job,
    map_slurm_state,
    SlurmJobInfo
)

logger = get_logger("remote_slurm_service")


class SlurmService:
    """Slurm作业管理服务"""
    
    @staticmethod
    def submit_job(
        task_id: str,
        username: str,
        workdir: str,
        commands: list,
        gpus: int = 0,
        cpus: int = 1,
        memory: str = '4G',
        time_limit: str = '1:00:00',
        partition: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """
        提交Slurm作业
        
        Args:
            task_id: 任务ID
            username: 用户名
            workdir: 工作目录（相对于用户目录）
            commands: 执行命令列表
            其他参数: 资源配置
            
        Returns:
            (success, job_id/error, message)
        """
        try:
            # 确定工作目录
            user_base = Path(REMOTE_BASE_DIR) / username
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = user_base / workdir
            
            # 确保目录存在
            work_path.mkdir(parents=True, exist_ok=True)
            
            # Slurm 输出文件路径
            slurm_dir = work_path / ".slurm"
            slurm_dir.mkdir(exist_ok=True)
            
            output_file = str(slurm_dir / f"{task_id}.out")
            error_file = str(slurm_dir / f"{task_id}.err")
            script_file = str(slurm_dir / f"{task_id}.sh")
            
            # 生成 Slurm 脚本
            script_content = generate_slurm_script(
                task_id=task_id,
                username=username,
                workdir=str(work_path),
                commands=commands if isinstance(commands, list) else [commands],
                gpus=gpus,
                cpus=cpus,
                memory=memory,
                time_limit=time_limit,
                output_file=output_file,
                error_file=error_file,
                partition=partition
            )
            
            # 写入脚本文件
            with open(script_file, 'w') as f:
                f.write(script_content)
            
            logger.info(f"生成 Slurm 脚本: {script_file}")
            
            # 提交 Slurm 作业
            success, result, stdout = submit_slurm_job(script_file)
            
            if success:
                logger.info(f"Slurm 作业提交成功: task={task_id}, job={result}")
                return True, result, f"Slurm 作业提交成功: {result}"
            else:
                logger.error(f"Slurm 作业提交失败: task={task_id}, error={result}")
                return False, result, f"Slurm 提交失败: {result}"
            
        except Exception as e:
            logger.error(f"提交任务异常: {e}")
            return False, str(e), f"提交任务失败: {e}"
    
    @staticmethod
    def get_job_status(job_id: str) -> Optional[SlurmJobInfo]:
        """获取Slurm作业状态"""
        return get_slurm_job_status(job_id)
    
    @staticmethod
    def cancel_job(job_id: str) -> Tuple[bool, str]:
        """取消Slurm作业"""
        return cancel_slurm_job(job_id)
    
    @staticmethod
    def map_job_state(slurm_state: str) -> str:
        """映射Slurm状态到统一状态"""
        return map_slurm_state(slurm_state)
