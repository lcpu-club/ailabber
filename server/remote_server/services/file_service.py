"""File Service - 文件管理服务"""
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from core.config import REMOTE_BASE_DIR
from utils.logger import get_logger
from utils.slurm import read_slurm_output

logger = get_logger("remote_file_service")


class FileService:
    """文件管理服务"""
    
    @staticmethod
    def read_logs(task_id: str, username: str, workdir: str = '.') -> tuple:
        """
        读取任务日志
        
        Args:
            task_id: 任务ID
            username: 用户名
            workdir: 工作目录
            
        Returns:
            (stdout, stderr)
        """
        try:
            # 构建日志路径
            user_base = Path(REMOTE_BASE_DIR) / username
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = user_base / workdir
            
            slurm_dir = work_path / ".slurm"
            output_file = slurm_dir / f"{task_id}.out"
            error_file = slurm_dir / f"{task_id}.err"
            
            stdout_content = read_slurm_output(str(output_file))
            stderr_content = read_slurm_output(str(error_file))
            
            return stdout_content, stderr_content
        except Exception as e:
            logger.error(f"读取日志失败: {e}")
            return "", ""
    
    @staticmethod
    def create_result_archive(
        task_id: str,
        username: str,
        workdir: str = '.',
        fetch_paths: list = []
    ) -> Optional[Path]:
        """
        创建结果归档文件
        
        Args:
            task_id: 任务ID
            username: 用户名
            workdir: 工作目录
            fetch_paths: 要获取的文件/目录列表
            
        Returns:
            zip文件路径或None
        """
        try:
            # 构建工作目录路径
            user_base = Path(REMOTE_BASE_DIR) / username
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = user_base / workdir
            
            # 创建临时 ZIP 文件
            temp_dir = tempfile.mkdtemp()
            zip_path = Path(temp_dir) / f"{task_id}_results.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 始终包含 Slurm 日志
                slurm_dir = work_path / ".slurm"
                for suffix in ['.out', '.err', '.sh']:
                    log_file = slurm_dir / f"{task_id}{suffix}"
                    if log_file.exists():
                        zf.write(log_file, f"slurm/{task_id}{suffix}")
                
                # 添加用户指定的路径
                if fetch_paths:
                    for rel_path in fetch_paths:
                        full_path = work_path / rel_path
                        if full_path.exists():
                            if full_path.is_file():
                                zf.write(full_path, rel_path)
                            elif full_path.is_dir():
                                for file_path in full_path.rglob('*'):
                                    if file_path.is_file():
                                        arc_name = str(file_path.relative_to(work_path))
                                        zf.write(file_path, arc_name)
            
            logger.info(f"创建结果归档: {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"创建结果归档失败: {e}")
            return None
