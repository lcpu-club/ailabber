#!/usr/bin/env python3
"""
Local Proxy Server - 本地代理服务器

功能：
1. 接收 CLI 任务提交请求
2. 本地任务：通过本地 Slurm 调度
3. 远程任务：同步文件到远程服务器，调用远程 API 提交 Slurm
4. 后台轮询任务状态
"""
import json
import zipfile
import tempfile
import shutil
import subprocess
import threading
import time
import requests
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file

from shared.config import (
    LOCAL_PROXY_PORT, 
    REMOTE_SERVER_PORT,
    REMOTE_SSH_HOST,
    REMOTE_SSH_PORT,
    REMOTE_SSH_USER,
    SSH_PRIVATE_KEY,
    REMOTE_BASE_DIR,
    REMOTE_SERVER_URL,
    LOCAL_TMP_DIR,
    POLL_INTERVAL
)
from shared.database import (
    init_local_db, 
    get_local_session, 
    TaskModel, 
    UserModel,
    MessageLogModel,
    Session
)
from utils.logger import get_logger
from utils.slurm import (
    generate_slurm_script,
    submit_slurm_job,
    get_slurm_job_status,
    cancel_slurm_job,
    map_slurm_state,
    read_slurm_output
)

# 初始化日志
logger = get_logger("local_proxy")

# 初始化 Flask 应用
app = Flask(__name__)

# 初始化数据库
init_local_db()

# 轮询线程控制
polling_thread = None
polling_stop_event = threading.Event()


# ============ 辅助函数 ============


def safe_update_task(session: Session, task: TaskModel, **kwargs):
    """安全更新任务字段"""
    try:
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.now()
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"更新任务失败: {task.task_id} - {e}")


def copy_uploads_to_tmp(username: str, upload_path: str, ignore_patterns: list[str]) -> str:
    """
    将上传文件复制到本地临时目录
    
    Args:
        username: 用户名
        upload_path: 上传目录路径
        ignore_patterns: 忽略的文件/目录列表
        
    Returns:
        tmp_path: 临时目录路径 (LOCAL_TMP_DIR/username)
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


def rsync_to_remote(username: str, local_path: str) -> bool:
    """
    使用 rsync 将本地目录同步到远程服务器
    
    Args:
        username: 用户名
        local_path: 本地目录路径
        
    Returns:
        success: 是否成功
    """
    # 远程目标路径: /home/{username}/
    remote_path = (Path(REMOTE_BASE_DIR) / username).as_posix() + "/"
    
    # 构建 rsync 命令
    rsync_cmd = "rsync -avz -e 'ssh -i {ssh_key} -p {ssh_port} -o StrictHostKeyChecking=no' {local}/ {user}@{host}:{remote}".format(
        ssh_key=SSH_PRIVATE_KEY,
        ssh_port=REMOTE_SSH_PORT,
        local=local_path,
        user=REMOTE_SSH_USER,
        host=REMOTE_SSH_HOST,
        remote=remote_path
    )
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


def rsync_from_remote(username: str, remote_paths: list[str], local_dest: str, workdir: str = ".") -> bool:
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
        
        rsync_cmd = "rsync -avz -e 'ssh -i {ssh_key} -p {ssh_port} -o StrictHostKeyChecking=no' {user}@{host}:{remote} {local}/".format(
            ssh_key=SSH_PRIVATE_KEY,
            ssh_port=REMOTE_SSH_PORT,
            user=REMOTE_SSH_USER,
            host=REMOTE_SSH_HOST,
            remote=remote_full,
            local=local_dest
        )
        
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


# ============ 本地 Slurm 提交 ============

def submit_local_slurm(session: Session, task: TaskModel, data: dict):
    """
    本地 Slurm 作业提交
    """
    username = data['username']
    task_id = task.task_id
    
    try:
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
            slurm_job_id = result
            safe_update_task(session, task, 
                status="running",
                slurm_job_id=slurm_job_id,
                started_at=datetime.now()
            )
            logger.info(f"本地 Slurm 作业提交成功: task={task_id}, job={slurm_job_id}")
            
            return jsonify({
                "task_id": task_id,
                "slurm_job_id": slurm_job_id,
                "message": f"本地 Slurm 作业提交成功: {slurm_job_id}",
                "target": "local"
            }), 200
        else:
            safe_update_task(session, task, status="failed")
            logger.error(f"本地 Slurm 提交失败: task={task_id}, error={result}")
            return jsonify({
                "error": result,
                "task_id": task_id,
                "message": f"本地 Slurm 提交失败: {result}"
            }), 500
            
    except Exception as e:
        logger.error(f"本地任务提交异常: {task_id} - {e}")
        safe_update_task(session, task, status="failed")
        return jsonify({
            "error": str(e),
            "task_id": task_id,
            "message": f"本地任务提交失败: {e}"
        }), 500


# ============ 远程 Slurm 提交 ============

def submit_remote_slurm(session: Session, task: TaskModel, data: dict):
    """
    远程 Slurm 作业提交
    1. 复制文件到临时目录
    2. rsync 到远程服务器
    3. 调用远程 API 提交 Slurm 作业
    """
    username = data['username']
    task_id = task.task_id
    upload_path = data.get('upload', '.')
    ignore_patterns = data.get('ignore', [])
    
    try:
        # 1. 复制文件到临时目录
        tmp_path = copy_uploads_to_tmp(username, upload_path, ignore_patterns)
        if not tmp_path:
            safe_update_task(session, task, status="failed")
            return jsonify({
                "error": "复制文件失败",
                "task_id": task_id,
                "message": "无法复制文件到临时目录"
            }), 500
        
        # 2. rsync 到远程服务器
        if not rsync_to_remote(username, tmp_path):
            safe_update_task(session, task, status="failed")
            return jsonify({
                "error": "rsync 失败",
                "task_id": task_id,
                "message": "无法同步文件到远程服务器"
            }), 500
        
        # 3. 调用远程 API 提交 Slurm
        commands = data.get('commands', [])
        if isinstance(commands, str):
            commands = commands.split(' && ')
        
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
        
        resp = requests.post(
            f"{REMOTE_SERVER_URL}/api/submit",
            json=remote_data,
            timeout=30
        )
        
        if resp.status_code == 200:
            result = resp.json()
            slurm_job_id = result.get('slurm_job_id')
            
            safe_update_task(session, task,
                status="running",
                slurm_job_id=slurm_job_id,
                started_at=datetime.now()
            )
            
            logger.info(f"远程 Slurm 作业提交成功: task={task_id}, job={slurm_job_id}")
            
            return jsonify({
                "task_id": task_id,
                "slurm_job_id": slurm_job_id,
                "message": f"远程 Slurm 作业提交成功: {slurm_job_id}",
                "target": "remote"
            }), 200
        else:
            error_msg = resp.json().get('message', '远程提交失败')
            safe_update_task(session, task, status="failed")
            logger.error(f"远程 Slurm 提交失败: task={task_id}, error={error_msg}")
            return jsonify({
                "error": error_msg,
                "task_id": task_id,
                "message": f"远程 Slurm 提交失败: {error_msg}"
            }), 500
            
    except requests.exceptions.RequestException as e:
        logger.error(f"远程服务器连接失败: {e}")
        safe_update_task(session, task, status="failed")
        return jsonify({
            "error": str(e),
            "task_id": task_id,
            "message": f"无法连接远程服务器: {e}"
        }), 500
    except Exception as e:
        logger.error(f"远程任务提交异常: {task_id} - {e}")
        safe_update_task(session, task, status="failed")
        return jsonify({
            "error": str(e),
            "task_id": task_id,
            "message": f"远程任务提交失败: {e}"
        }), 500


# ============ 状态轮询 ============

def poll_task_status():
    """后台轮询任务状态"""
    logger.info("启动任务状态轮询线程")
    
    while not polling_stop_event.is_set():
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
                        # 本地 Slurm 状态查询 (包括 local-run)
                        job_info = get_slurm_job_status(task.slurm_job_id)
                        if job_info:
                            new_status = map_slurm_state(job_info.state)
                            update_task_from_slurm(session, task, job_info, new_status)
                    
                    elif task.target == 'remote':
                        # 远程 Slurm 状态查询
                        try:
                            resp = requests.get(
                                f"{REMOTE_SERVER_URL}/api/status/{task.slurm_job_id}",
                                timeout=10
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                new_status = data.get('status', task.status)
                                
                                if new_status != task.status:
                                    task.status = new_status
                                    if new_status in ['completed', 'failed', 'canceled']:
                                        task.completed_at = datetime.now()
                                        task.exit_code = data.get('exit_code')
                                    task.updated_at = datetime.now()
                                    session.commit()
                                    logger.info(f"任务状态更新: {task.task_id} -> {new_status}")
                        except requests.exceptions.RequestException as e:
                            logger.warning(f"查询远程任务状态失败: {task.task_id} - {e}")
                
                except Exception as e:
                    logger.error(f"轮询任务 {task.task_id} 失败: {e}")
            
            session.close()
            
        except Exception as e:
            logger.error(f"轮询循环异常: {e}")
        
        # 等待下一次轮询
        polling_stop_event.wait(POLL_INTERVAL)
    
    logger.info("任务状态轮询线程已停止")


def update_task_from_slurm(session: Session, task: TaskModel, job_info, new_status: str):
    """根据 Slurm 作业信息更新任务状态"""
    if new_status != task.status:
        task.status = new_status
        
        if new_status in ['completed', 'failed', 'canceled']:
            task.completed_at = datetime.now()
            task.exit_code = job_info.exit_code
        
        task.updated_at = datetime.now()
        session.commit()
        logger.info(f"任务状态更新: {task.task_id} -> {new_status}")


def start_polling_thread():
    """启动轮询线程"""
    global polling_thread
    if polling_thread is None or not polling_thread.is_alive():
        polling_stop_event.clear()
        polling_thread = threading.Thread(target=poll_task_status, daemon=True)
        polling_thread.start()


def stop_polling_thread():
    """停止轮询线程"""
    polling_stop_event.set()
    if polling_thread:
        polling_thread.join(timeout=5)
# ============ API 路由 ============

@app.route('/api/submit', methods=['POST'])
def submit_task():
    """
    提交任务
    
    请求体:
    {
        "username": str,
        "target": str,           # "local" 或 "remote"
        "upload": str,           # 上传目录路径
        "ignore": list[str],     # 忽略的文件列表
        "workdir": str,          # 工作目录
        "commands": list[str],   # 执行命令列表
        "logs": list[str],       # 日志路径列表
        "results": list[str],    # 结果路径列表
        "gpus": int,
        "cpus": int,
        "memory": str,
        "time_limit": str,
        "partition": str (可选)
    }
    
    返回:
    {
        "task_id": str,
        "slurm_job_id": str,
        "message": str,
        "target": str
    }
    """
    try:
        data = request.get_json()
        
        # 验证必要字段
        required_fields = ['username', 'commands']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "error": f"缺少必要字段: {field}",
                    "message": f"缺少必要字段: {field}"
                }), 400
        
        username = data['username']
        target = data.get('target', 'local')
        
        # 合并命令
        commands = data.get('commands', [])
        command_str = ' && '.join(commands) if isinstance(commands, list) else commands
        
        # 创建数据库会话和任务记录
        session = get_local_session()
        try:
            task = TaskModel(
                username=username,
                status="pending",
                target=target,
                upload=data.get('upload', '.'),
                ignore=json.dumps(data.get('ignore', []), ensure_ascii=False),
                commands=command_str,
                workdir=data.get('workdir', '.'),
                logs_path=json.dumps(data.get('logs', []), ensure_ascii=False),
                results_path=json.dumps(data.get('results', []), ensure_ascii=False),
                gpus=data.get('gpus', 0),
                cpus=data.get('cpus', 1),
                memory=data.get('memory', '4G'),
                time_limit=data.get('time_limit', '1:00:00'),
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
            
            # 根据目标提交任务
            if target == "local":
                return submit_local_slurm(session, task, data)
            elif target == "remote":
                return submit_remote_slurm(session, task, data)
            else:
                return jsonify({
                    "error": f"未知目标: {target}",
                    "message": f"目标类型必须是 'local' 或 'remote'"
                }), 400
            
        except Exception as e:
            session.rollback()
            logger.error(f"创建任务失败: {e}")
            return jsonify({
                "error": str(e),
                "message": f"创建任务失败: {e}"
            }), 500
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"处理请求失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"处理请求失败: {e}"
        }), 500


@app.route('/api/local-run', methods=['POST'])
def create_local_run_task():
    """
    Create DB record for local-run (does NOT submit Slurm job)
    CLI will submit Slurm job directly after getting task_id
    
    Request:
    {
        "username": str,
        "workdir": str,
        "commands": [str],
        "gpus": int,
        "cpus": int,
        "memory": str,
        "time_limit": str
    }
    
    Response:
    {
        "task_id": str
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        username = data.get('username')
        if not username:
            return jsonify({"error": "Username is required"}), 400
        
        session = get_local_session()
        try:
            # Create task record (pending status, no slurm_job_id yet)
            task = TaskModel(
                username=username,
                status="pending",
                target="local-run",
                workdir=data.get('workdir', '.'),
                commands=json.dumps(data.get('commands', [])),
                gpus=data.get('gpus', 0),
                cpus=data.get('cpus', 1),
                memory=data.get('memory', '4G'),
                time_limit=data.get('time_limit', '1:00:00'),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(task)
            
            # Update user stats
            user = session.query(UserModel).filter_by(username=username).first()
            if user:
                user.total_tasks += 1
            
            session.commit()
            task_id = task.task_id
            
            logger.info(f"Created local-run task record: {task_id}")
            
            return jsonify({"task_id": task_id}), 200
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create task: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Request processing failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/local-run/<task_id>/slurm', methods=['POST'])
def update_local_run_slurm(task_id: str):
    """
    Update task with Slurm job ID after CLI submits the job
    
    Request:
    {
        "slurm_job_id": str
    }
    """
    try:
        data = request.get_json()
        slurm_job_id = data.get('slurm_job_id')
        
        if not slurm_job_id:
            return jsonify({"error": "slurm_job_id is required"}), 400
        
        session = get_local_session()
        try:
            task = session.query(TaskModel).filter_by(task_id=task_id).first()
            
            if not task:
                return jsonify({"error": "Task not found"}), 404
            
            task.slurm_job_id = slurm_job_id
            task.status = "running"
            task.started_at = datetime.now()
            task.updated_at = datetime.now()
            session.commit()
            
            logger.info(f"Updated task {task_id} with Slurm job {slurm_job_id}")
            
            return jsonify({"message": "Updated successfully"}), 200
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update task: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Request processing failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/status/<task_id>', methods=['GET'])
def get_task_status(task_id: str):
    """
    获取任务状态
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
    
    返回:
    {
        "task": {
            "task_id": str,
            "username": str,
            "status": str,
            "created_at": str,
            ...
        }
    }
    """
    username = request.args.get('username')
    
    session = get_local_session()
    try:
        task = session.query(TaskModel).filter_by(task_id=task_id).first()
        
        if not task:
            return jsonify({
                "error": "任务不存在",
                "message": f"任务 {task_id} 不存在"
            }), 404
        
        # 验证用户权限
        if username and task.username != username:
            return jsonify({
                "error": "无权限",
                "message": "您没有权限查看此任务"
            }), 403
        
        return jsonify({
            "task": task.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"查询任务状态失败: {e}"
        }), 500
    finally:
        session.close()


@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    """
    列出用户的所有任务
    
    参数:
        username: 用户名 (query param)
        status: 状态过滤 (query param, 可选)
    
    返回:
    {
        "tasks": [
            {
                "task_id": str,
                "username": str,
                "status": str,
                "created_at": str
            },
            ...
        ]
    }
    """
    username = request.args.get('username')
    status = request.args.get('status')
    
    if not username:
        return jsonify({
            "error": "缺少用户名",
            "message": "请提供用户名参数"
        }), 400
    
    session = get_local_session()
    try:
        query = session.query(TaskModel).filter_by(username=username)
        
        if status:
            query = query.filter_by(status=status)
        
        tasks = query.order_by(TaskModel.created_at.desc()).all()
        
        return jsonify({
            "tasks": [task.to_dict() for task in tasks]
        }), 200
        
    except Exception as e:
        logger.error(f"列出任务失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"列出任务失败: {e}"
        }), 500
    finally:
        session.close()


@app.route('/api/fetch/<task_id>', methods=['GET'])
def fetch_task_results(task_id: str):
    """
    获取任务结果文件
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
    
    返回:
        - 本地任务: 直接返回 ZIP 文件
        - 远程任务: 从远程下载后返回
    """
    username = request.args.get('username')
    
    session = get_local_session()
    try:
        task = session.query(TaskModel).filter_by(task_id=task_id).first()
        
        if not task:
            return jsonify({
                "error": "任务不存在",
                "message": f"任务 {task_id} 不存在"
            }), 404
        
        # 验证用户权限
        if username and task.username != username:
            return jsonify({
                "error": "无权限",
                "message": "您没有权限查看此任务"
            }), 403
        
        # 解析要获取的路径
        logs_paths = json.loads(task.logs_path or '[]')
        results_paths = json.loads(task.results_path or '[]')
        fetch_paths = logs_paths + results_paths
        
        if task.target == 'local':
            # 本地任务 - 直接打包
            upload_path = Path(task.upload) if task.upload else Path('.')
            workdir = task.workdir or '.'
            
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = upload_path / workdir if upload_path.exists() else Path(workdir)
            work_path = work_path.resolve()
            
            # 创建 ZIP
            temp_dir = tempfile.mkdtemp()
            zip_path = Path(temp_dir) / f"{task_id}_results.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Slurm 日志
                slurm_dir = work_path / ".slurm"
                for suffix in ['.out', '.err', '.sh']:
                    log_file = slurm_dir / f"{task_id}{suffix}"
                    if log_file.exists():
                        zf.write(log_file, f"slurm/{task_id}{suffix}")
                
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
            
            return send_file(
                zip_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{task_id}_results.zip"
            )
        
        elif task.target == 'remote':
            # 远程任务 - 调用远程 API
            try:
                import urllib.parse
                paths_param = urllib.parse.quote(json.dumps(fetch_paths))
                
                resp = requests.get(
                    f"{REMOTE_SERVER_URL}/api/fetch/{task_id}",
                    params={
                        "username": task.username,
                        "workdir": task.workdir,
                        "paths": json.dumps(fetch_paths)
                    },
                    timeout=300,
                    stream=True
                )
                
                if resp.status_code == 200:
                    # 保存到临时文件
                    temp_dir = tempfile.mkdtemp()
                    zip_path = Path(temp_dir) / f"{task_id}_results.zip"
                    
                    with open(zip_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    return send_file(
                        zip_path,
                        mimetype='application/zip',
                        as_attachment=True,
                        download_name=f"{task_id}_results.zip"
                    )
                else:
                    return jsonify({
                        "error": "获取远程结果失败",
                        "message": resp.json().get('message', '未知错误')
                    }), resp.status_code
                    
            except requests.exceptions.RequestException as e:
                return jsonify({
                    "error": str(e),
                    "message": f"无法连接远程服务器: {e}"
                }), 500
        
    except Exception as e:
        logger.error(f"获取任务结果失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取任务结果失败: {e}"
        }), 500
    finally:
        session.close()


@app.route('/api/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id: str):
    """
    取消任务
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
    
    返回:
    {
        "message": str,
        "status": str
    }
    """
    username = request.args.get('username')
    
    session = get_local_session()
    try:
        task = session.query(TaskModel).filter_by(task_id=task_id).first()
        
        if not task:
            return jsonify({
                "error": "任务不存在",
                "message": f"任务 {task_id} 不存在"
            }), 404
        
        # 验证用户权限
        if username and task.username != username:
            return jsonify({
                "error": "无权限",
                "message": "您没有权限取消此任务"
            }), 403
        
        # 已完成的任务无法取消
        if task.status in ['completed', 'failed', 'canceled']:
            return jsonify({
                "message": f"任务已是 {task.status} 状态",
                "status": task.status
            }), 400
        
        old_status = task.status
        
        # 如果有 Slurm 作业，需要取消
        if task.slurm_job_id:
            if task.target == 'local':
                success, message = cancel_slurm_job(task.slurm_job_id)
                if not success:
                    logger.warning(f"取消本地 Slurm 作业失败: {message}")
            elif task.target == 'remote':
                try:
                    resp = requests.post(
                        f"{REMOTE_SERVER_URL}/api/cancel/{task.slurm_job_id}",
                        timeout=10
                    )
                    if resp.status_code != 200:
                        logger.warning(f"取消远程 Slurm 作业失败: {resp.json()}")
                except Exception as e:
                    logger.warning(f"取消远程作业异常: {e}")
        
        # 更新状态
        task.status = 'canceled'
        task.completed_at = datetime.now()
        task.updated_at = datetime.now()
        
        # 记录日志
        msg_log = MessageLogModel(
            msg_type="task_cancel",
            direction="outgoing",
            payload=json.dumps({
                "task_id": task_id,
                "old_status": old_status,
                "new_status": "canceled"
            }),
            created_at=datetime.now()
        )
        session.add(msg_log)
        session.commit()
        
        logger.info(f"任务已取消: {task_id}")
        
        return jsonify({
            "message": f"任务 {task_id} 已取消",
            "status": "canceled"
        }), 200
        
    except Exception as e:
        session.rollback()
        logger.error(f"取消任务失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"取消任务失败: {e}"
        }), 500
    finally:
        session.close()


@app.route('/api/logs/<task_id>', methods=['GET'])
def get_task_logs(task_id: str):
    """
    获取任务执行日志（不下载文件）
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
    
    返回:
    {
        "task_id": str,
        "stdout": str,
        "stderr": str
    }
    """
    username = request.args.get('username')
    
    session = get_local_session()
    try:
        task = session.query(TaskModel).filter_by(task_id=task_id).first()
        
        if not task:
            return jsonify({
                "error": "任务不存在",
                "message": f"任务 {task_id} 不存在"
            }), 404
        
        if username and task.username != username:
            return jsonify({
                "error": "无权限",
                "message": "您没有权限查看此任务"
            }), 403
        
        if task.target == 'local':
            # 本地任务 - 直接读取日志
            upload_path = Path(task.upload) if task.upload else Path('.')
            workdir = task.workdir or '.'
            
            if workdir.startswith('/'):
                work_path = Path(workdir)
            else:
                work_path = upload_path / workdir if upload_path.exists() else Path(workdir)
            work_path = work_path.resolve()
            
            slurm_dir = work_path / ".slurm"
            stdout = read_slurm_output(str(slurm_dir / f"{task_id}.out"))
            stderr = read_slurm_output(str(slurm_dir / f"{task_id}.err"))
            
            return jsonify({
                "task_id": task_id,
                "stdout": stdout,
                "stderr": stderr
            }), 200
            
        elif task.target == 'remote':
            # 远程任务 - 调用远程 API
            try:
                resp = requests.get(
                    f"{REMOTE_SERVER_URL}/api/logs/{task_id}",
                    params={
                        "username": task.username,
                        "workdir": task.workdir
                    },
                    timeout=30
                )
                
                if resp.status_code == 200:
                    return jsonify(resp.json()), 200
                else:
                    return jsonify(resp.json()), resp.status_code
                    
            except requests.exceptions.RequestException as e:
                return jsonify({
                    "error": str(e),
                    "message": f"无法连接远程服务器: {e}"
                }), 500
        
    except Exception as e:
        logger.error(f"获取任务日志失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取任务日志失败: {e}"
        }), 500
    finally:
        session.close()


# ============ 健康检查 ============

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "service": "local_proxy",
        "timestamp": datetime.now().isoformat(),
        "polling_active": polling_thread is not None and polling_thread.is_alive()
    }), 200


@app.route('/', methods=['GET'])
def index():
    """根路径 - API 文档"""
    return jsonify({
        "service": "ailabber Local Proxy",
        "version": "2.0.0",
        "description": "本地代理服务器 - 支持本地/远程 Slurm 调度",
        "endpoints": [
            "POST /api/submit - 提交任务",
            "GET /api/status/<task_id> - 获取任务状态",
            "GET /api/tasks - 列出用户任务",
            "GET /api/logs/<task_id> - 获取任务日志",
            "GET /api/fetch/<task_id> - 下载任务结果",
            "POST /api/cancel/<task_id> - 取消任务",
            "GET /health - 健康检查"
        ]
    }), 200


# ============ 主入口 ============

def main():
    """启动服务器"""
    # 启动轮询线程
    start_polling_thread()
    
    logger.info(f"Local Proxy 服务器启动于端口 {LOCAL_PROXY_PORT}")
    
    try:
        app.run(
            host='127.0.0.1',
            port=LOCAL_PROXY_PORT,
            debug=False,
            threaded=True
        )
    finally:
        stop_polling_thread()


if __name__ == '__main__':
    main()
