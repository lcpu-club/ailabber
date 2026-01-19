#!/usr/bin/env python3
"""
Slurm 工具模块 - 封装 Slurm 相关操作
"""
import subprocess
import re
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from utils.logger import get_logger

logger = get_logger("slurm")


@dataclass
class SlurmJobInfo:
    """Slurm 作业信息"""
    job_id: str
    state: str  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, TIMEOUT
    exit_code: Optional[int] = None
    node: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


# Slurm 状态映射到统一状态
SLURM_STATE_MAP = {
    "PENDING": "pending",
    "RUNNING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "CANCELLED": "canceled",
    "TIMEOUT": "failed",
    "NODE_FAIL": "failed",
    "PREEMPTED": "failed",
    "OUT_OF_MEMORY": "failed",
}


def generate_slurm_script(
    task_id: str,
    username: str,
    workdir: str,
    commands: list[str],
    gpus: int = 0,
    cpus: int = 1,
    memory: str = "4G",
    time_limit: str = "1:00:00",
    job_name: Optional[str] = None,
    output_file: Optional[str] = None,
    error_file: Optional[str] = None,
    partition: Optional[str] = None,
) -> str:
    """
    生成 Slurm 批处理脚本
    
    Args:
        task_id: 任务ID
        username: 用户名
        workdir: 工作目录
        commands: 要执行的命令列表
        gpus: GPU 数量
        cpus: CPU 核心数
        memory: 内存大小 (如 "32G")
        time_limit: 时间限制 (如 "4:00:00")
        job_name: 作业名称
        output_file: 标准输出文件路径
        error_file: 标准错误文件路径
        partition: Slurm 分区
        
    Returns:
        slurm_script: Slurm 脚本内容
    """
    job_name = job_name or f"ailabber_{task_id}"
    output_file = output_file or f"slurm_{task_id}.out"
    error_file = error_file or f"slurm_{task_id}.err"
    
    script_lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --output={output_file}",
        f"#SBATCH --error={error_file}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --cpus-per-task={cpus}",
        f"#SBATCH --mem={memory}",
    ]
    
    # GPU 配置
    if gpus > 0:
        script_lines.append(f"#SBATCH --gres=gpu:{gpus}")
    
    # 分区配置
    if partition:
        script_lines.append(f"#SBATCH --partition={partition}")
    
    # 添加空行和环境设置
    script_lines.extend([
        "",
        "# 任务信息",
        f"echo 'Task ID: {task_id}'",
        f"echo 'User: {username}'",
        f"echo 'Start Time: '$(date)",
        f"echo 'Working Directory: {workdir}'",
        "echo '----------------------------------------'",
        "",
        "# 切换到工作目录",
        f"cd {workdir}",
        "",
        "# 执行命令",
    ])
    
    # 添加用户命令
    for cmd in commands:
        script_lines.append(cmd)
    
    # 添加结束标记
    script_lines.extend([
        "",
        "echo '----------------------------------------'",
        "echo 'End Time: '$(date)",
        f"echo 'Task {task_id} finished with exit code: '$?",
    ])
    
    return "\n".join(script_lines)


def submit_slurm_job(script_path: str) -> Tuple[bool, str, str]:
    """
    提交 Slurm 作业
    
    Args:
        script_path: Slurm 脚本路径
        
    Returns:
        (success, job_id/error_message, stdout)
    """
    try:
        result = subprocess.run(
            ["sbatch", script_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # 解析 job_id: "Submitted batch job 12345"
            match = re.search(r"Submitted batch job (\d+)", result.stdout)
            if match:
                job_id = match.group(1)
                logger.info(f"Slurm 作业提交成功: {job_id}")
                return True, job_id, result.stdout
            else:
                logger.error(f"无法解析 Slurm 输出: {result.stdout}")
                return False, "无法解析作业ID", result.stdout
        else:
            logger.error(f"Slurm 提交失败: {result.stderr}")
            return False, result.stderr, result.stdout
            
    except subprocess.TimeoutExpired:
        logger.error("Slurm 提交超时")
        return False, "提交超时", ""
    except FileNotFoundError:
        logger.error("sbatch 命令未找到，请确认 Slurm 已安装")
        return False, "sbatch 命令未找到", ""
    except Exception as e:
        logger.error(f"Slurm 提交异常: {e}")
        return False, str(e), ""


def get_slurm_job_status(job_id: str) -> Optional[SlurmJobInfo]:
    """
    查询 Slurm 作业状态
    
    Args:
        job_id: Slurm 作业ID
        
    Returns:
        SlurmJobInfo 或 None
    """
    try:
        # 使用 sacct 查询作业状态（包括已完成的作业）
        result = subprocess.run(
            [
                "sacct", "-j", job_id,
                "--format=JobID,State,ExitCode,NodeList,Start,End",
                "--noheader", "--parsable2"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            # 尝试使用 squeue 查询（仅限运行中的作业）
            result = subprocess.run(
                ["squeue", "-j", job_id, "-h", "-o", "%i|%T|%N|%S"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 2:
                    return SlurmJobInfo(
                        job_id=parts[0],
                        state=parts[1],
                        node=parts[2] if len(parts) > 2 else None,
                        start_time=parts[3] if len(parts) > 3 else None
                    )
            return None
        
        # 解析 sacct 输出
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if not line or ".batch" in line or ".extern" in line:
                continue
            parts = line.split("|")
            if len(parts) >= 2:
                # ExitCode 格式: "0:0"
                exit_code = None
                if len(parts) >= 3 and ":" in parts[2]:
                    try:
                        exit_code = int(parts[2].split(":")[0])
                    except ValueError:
                        pass
                
                return SlurmJobInfo(
                    job_id=parts[0],
                    state=parts[1],
                    exit_code=exit_code,
                    node=parts[3] if len(parts) > 3 and parts[3] else None,
                    start_time=parts[4] if len(parts) > 4 and parts[4] != "Unknown" else None,
                    end_time=parts[5] if len(parts) > 5 and parts[5] != "Unknown" else None
                )
        
        return None
        
    except subprocess.TimeoutExpired:
        logger.error(f"查询作业 {job_id} 状态超时")
        return None
    except FileNotFoundError:
        logger.error("sacct/squeue 命令未找到")
        return None
    except Exception as e:
        logger.error(f"查询作业状态异常: {e}")
        return None


def cancel_slurm_job(job_id: str) -> Tuple[bool, str]:
    """
    取消 Slurm 作业
    
    Args:
        job_id: Slurm 作业ID
        
    Returns:
        (success, message)
    """
    try:
        result = subprocess.run(
            ["scancel", job_id],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.info(f"Slurm 作业已取消: {job_id}")
            return True, f"作业 {job_id} 已取消"
        else:
            logger.error(f"取消作业失败: {result.stderr}")
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        return False, "取消操作超时"
    except FileNotFoundError:
        return False, "scancel 命令未找到"
    except Exception as e:
        return False, str(e)


def map_slurm_state(slurm_state: str) -> str:
    """将 Slurm 状态映射为统一状态"""
    # 处理带有原因的状态，如 "PENDING (Resources)"
    base_state = slurm_state.split()[0] if slurm_state else "UNKNOWN"
    return SLURM_STATE_MAP.get(base_state, "unknown")


def read_slurm_output(output_file: str, max_lines: int = 1000) -> str:
    """
    读取 Slurm 输出文件
    
    Args:
        output_file: 输出文件路径
        max_lines: 最大读取行数
        
    Returns:
        文件内容
    """
    try:
        path = Path(output_file)
        if not path.exists():
            return ""
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            if len(lines) > max_lines:
                return "... (truncated) ...\n" + "".join(lines[-max_lines:])
            return "".join(lines)
    except Exception as e:
        logger.error(f"读取输出文件失败: {e}")
        return f"读取失败: {e}"
