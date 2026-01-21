"""File Service - 文件同步和管理服务"""
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from core.config import (
    LOCAL_TMP_DIR,
    REMOTE_SSH_HOST,
    REMOTE_SSH_PORT,
    REMOTE_SSH_USER,
    SSH_PRIVATE_KEY,
    REMOTE_BASE_DIR
)
from core.database import TaskModel
from utils.logger import get_logger
from utils.slurm import read_slurm_output

logger = get_logger("file_service")


class FileService:
    """文件同步和管理服务"""
    
    @staticmethod
    def copy_to_temp(
        username: str,
        upload_path: str,
        ignore_patterns: list
    ) -> str:
        """
        将上传文件复制到本地临时目录
        
        Args:
            username: 用户名
            upload_path: 上传目录路径
            ignore_patterns: 忽略的文件/目录列表
            
        Returns:
            tmp_path: 临时目录路径
        """
        upload_dir = Path(upload_path)
        if not upload_dir.exists():
            logger.error(f"{username} - upload_dir does not exist: {upload_path}")
            return ""
        
        # 创建用户临时目录
        tmp_dir = LOCAL_TMP_DIR / username
        
        # 如果目录已存在，先清空
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        # 将 ignore_patterns 转换为绝对路径集合
        ignore_set = set(Path(p).resolve() for p in ignore_patterns if p)
        
        def should_ignore(file_path: Path) -> bool:
            """检查文件是否应该被忽略"""
            # 检查文件本身
            if file_path.resolve() in ignore_set:
                return True
            # 检查父目录
            for parent in file_path.parents:
                if parent.resolve() in ignore_set:
                    return True
            return False
        
        # 复制文件
        for file_path in upload_dir.rglob('*'):
            if should_ignore(file_path):
                continue
            
            rel_path = file_path.relative_to(upload_dir)
            target_path = tmp_dir / rel_path
            
            if file_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            elif file_path.is_file():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)
        
        logger.info(f"{username} - files copied to tmp dir: {tmp_dir}")
        return str(tmp_dir)
    
    @staticmethod
    def rsync_to_remote(username: str, local_path: str) -> bool:
        """
        使用 rsync 将本地目录同步到远程服务器
        
        Args:
            username: 用户名
            local_path: 本地目录路径
            
        Returns:
            success: 是否成功
        """
        # 远程目标路径
        remote_path = (Path(REMOTE_BASE_DIR) / username).as_posix() + "/"
        
        # 构建 rsync 命令
        rsync_cmd = f"rsync -avz -e \"ssh -i {SSH_PRIVATE_KEY} -p {REMOTE_SSH_PORT} -o StrictHostKeyChecking=no\" {local_path}/ {REMOTE_SSH_USER}@{REMOTE_SSH_HOST}:{remote_path}"
        
        logger.info(f"{username} - rsync: {rsync_cmd}")
        
        try:
            result = subprocess.run(
                rsync_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=3600  # 1小时超时
            )
            
            if result.returncode == 0:
                logger.info(f"{username} - rsync success: {local_path} -> {remote_path}")
                return True
            else:
                logger.error(f"{username} - rsync failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"{username} - rsync timeout")
            return False
        except Exception as e:
            logger.error(f"{username} - rsync exception: {e}")
            return False
    
    @staticmethod
    def rsync_from_remote(
        username: str,
        remote_paths: list,
        local_dest: str,
        workdir: str = "."
    ) -> bool:
        """
        从远程服务器同步文件到本地
        
        Args:
            username: 用户名
            remote_paths: 远程路径列表（相对于工作目录）
            local_dest: 本地目标目录
            workdir: 远程工作目录
            
        Returns:
            success: 是否成功
        """
        user_base = Path(REMOTE_BASE_DIR) / username
        if workdir.startswith('/'):
            work_path = Path(workdir)
        else:
            work_path = user_base / workdir
        
        success = True
        for rel_path in remote_paths:
            remote_full = (work_path / rel_path).as_posix()
            
            rsync_cmd = f"rsync -avz -e \"ssh -i {SSH_PRIVATE_KEY} -p {REMOTE_SSH_PORT} -o StrictHostKeyChecking=no\" {REMOTE_SSH_USER}@{REMOTE_SSH_HOST}:{remote_full} {local_dest}/"
            
            try:
                result = subprocess.run(
                    rsync_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=3600
                )
                
                if result.returncode != 0:
                    logger.error(f"rsync from remote failed: {result.stderr}")
                    success = False
            except Exception as e:
                logger.error(f"rsync from remote exception: {e}")
                success = False
        
        return success
    
    @staticmethod
    def create_local_result_archive(task: TaskModel) -> Optional[Path]:
        """
        为本地任务创建结果归档文件
        
        Args:
            task: 任务对象
            
        Returns:
            zip文件路径或None
        """
        try:
            upload_path = Path(task.upload) if task.upload else Path('.')
            workdir = task.workdir or '.'
            
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = upload_path / workdir if upload_path.exists() else Path(workdir)
            work_path = work_path.resolve()
            
            # 解析要获取的路径
            logs_paths = json.loads(task.logs_path or '[]')
            results_paths = json.loads(task.results_path or '[]')
            fetch_paths = logs_paths + results_paths
            
            # 创建 ZIP
            temp_dir = tempfile.mkdtemp()
            zip_path = Path(temp_dir) / f"{task.task_id}_results.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Slurm 日志
                slurm_dir = work_path / ".slurm"
                for suffix in ['.out', '.err', '.sh']:
                    log_file = slurm_dir / f"{task.task_id}{suffix}"
                    if log_file.exists():
                        zf.write(log_file, f"slurm/{task.task_id}{suffix}")
                
                # 用户指定的路径
                for rel_path in fetch_paths:
                    full_path = work_path / rel_path
                    if full_path.exists():
                        if full_path.is_file():
                            zf.write(full_path, rel_path)
                        elif full_path.is_dir():
                            for fp in full_path.rglob('*'):
                                if fp.is_file():
                                    arc_name = str(fp.relative_to(work_path))
                                    zf.write(fp, arc_name)
            
            logger.info(f"创建本地结果归档: {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"创建结果归档失败: {e}")
            return None
    
    @staticmethod
    def read_local_logs(task: TaskModel) -> tuple:
        """
        读取本地任务日志
        
        Args:
            task: 任务对象
            
        Returns:
            (stdout, stderr)
        """
        try:
            upload_path = Path(task.upload) if task.upload else Path('.')
            workdir = task.workdir or '.'
            
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = upload_path / workdir if upload_path.exists() else Path(workdir)
            work_path = work_path.resolve()
            
            slurm_dir = work_path / ".slurm"
            stdout = read_slurm_output(str(slurm_dir / f"{task.task_id}.out"))
            stderr = read_slurm_output(str(slurm_dir / f"{task.task_id}.err"))
            
            return stdout, stderr
        except Exception as e:
            logger.error(f"读取本地日志失败: {e}")
            return "", ""
