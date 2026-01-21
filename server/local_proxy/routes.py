"""Routes - Flask路由层（轻量级）"""
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
import requests

from core.database import get_local_session
from core.config import REMOTE_SERVER_URL
from utils.logger import get_logger

from .services import (
    TaskService,
    LocalSlurmService,
    RemoteSlurmService,
    FileService,
    get_polling_service
)

logger = get_logger("routes")

# 创建蓝图
api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/submit', methods=['POST'])
def submit_task():
    """提交任务"""
    session = None
    try:
        data = request.get_json()
        
        # 验证必要字段
        if 'username' not in data or 'commands' not in data:
            return jsonify({"error": "缺少必要字段", "message": "需要username和commands"}), 400
        
        username = data['username']
        target = data.get('target', 'local')
        
        session = get_local_session()
        
        # 创建任务
        task = TaskService.create_task(
            session=session,
            username=username,
            target=target,
            commands=data.get('commands', []),
            upload=data.get('upload', '.'),
            ignore=data.get('ignore', []),
            workdir=data.get('workdir', '.'),
            logs_path=data.get('logs', []),
            results_path=data.get('results', []),
            gpus=data.get('gpus', 0),
            cpus=data.get('cpus', 1),
            memory=data.get('memory', '4G'),
            time_limit=data.get('time_limit', '1:00:00')
        )
        
        task_id = task.task_id
        
        # 根据目标提交任务
        if target == "local":
            success, result, message = LocalSlurmService.submit_job(task, data)
            
            if success:
                TaskService.update_task_status(session, task, "running", slurm_job_id=result)
                return jsonify({
                    "task_id": task_id,
                    "slurm_job_id": result,
                    "message": message,
                    "target": "local"
                }), 200
            else:
                TaskService.update_task_status(session, task, "failed")
                return jsonify({
                    "error": result,
                    "task_id": task_id,
                    "message": message
                }), 500
        
        elif target == "remote":
            # 先同步文件
            upload_path = data.get('upload', '.')
            ignore_patterns = data.get('ignore', [])
            
            tmp_path = FileService.copy_to_temp(username, upload_path, ignore_patterns)
            if not tmp_path:
                TaskService.update_task_status(session, task, "failed")
                return jsonify({
                    "error": "复制文件失败",
                    "task_id": task_id,
                    "message": "无法复制文件到临时目录"
                }), 500
            
            if not FileService.rsync_to_remote(username, tmp_path):
                TaskService.update_task_status(session, task, "failed")
                return jsonify({
                    "error": "rsync 失败",
                    "task_id": task_id,
                    "message": "无法同步文件到远程服务器"
                }), 500
            
            # 提交到远程
            success, result, message = RemoteSlurmService.submit_job(task, data)
            
            if success:
                TaskService.update_task_status(session, task, "running", slurm_job_id=result)
                return jsonify({
                    "task_id": task_id,
                    "slurm_job_id": result,
                    "message": message,
                    "target": "remote"
                }), 200
            else:
                TaskService.update_task_status(session, task, "failed")
                return jsonify({
                    "error": result,
                    "task_id": task_id,
                    "message": message
                }), 500
        else:
            return jsonify({
                "error": f"未知目标: {target}",
                "message": "目标类型必须是 'local' 或 'remote'"
            }), 400
    
    except Exception as e:
        logger.error(f"处理请求失败: {e}")
        return jsonify({"error": str(e), "message": f"处理请求失败: {e}"}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/local-run', methods=['POST'])
def create_local_run_task():
    """创建local-run任务记录（CLI会自己提交Slurm）"""
    session = None
    try:
        data = request.get_json()
        if not data or 'username' not in data:
            return jsonify({"error": "Invalid JSON data or missing username"}), 400
        
        session = get_local_session()
        
        task = TaskService.create_task(
            session=session,
            username=data['username'],
            target="local-run",
            commands=data.get('commands', []),
            workdir=data.get('workdir', '.'),
            gpus=data.get('gpus', 0),
            cpus=data.get('cpus', 1),
            memory=data.get('memory', '4G'),
            time_limit=data.get('time_limit', '1:00:00')
        )
        
        logger.info(f"Created local-run task record: {task.task_id}")
        return jsonify({"task_id": task.task_id}), 200
    
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/local-run/<task_id>/slurm', methods=['POST'])
def update_local_run_slurm(task_id: str):
    """更新local-run任务的Slurm作业ID"""
    session = None
    try:
        data = request.get_json()
        slurm_job_id = data.get('slurm_job_id')
        
        if not slurm_job_id:
            return jsonify({"error": "slurm_job_id is required"}), 400
        
        session = get_local_session()
        task = TaskService.get_task(session, task_id)
        
        if not task:
            return jsonify({"error": "Task not found"}), 404
        
        TaskService.update_task_status(session, task, "running", slurm_job_id=slurm_job_id)
        logger.info(f"Updated task {task_id} with Slurm job {slurm_job_id}")
        
        return jsonify({"message": "Updated successfully"}), 200
    
    except Exception as e:
        logger.error(f"Failed to update task: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id: str):
    """获取任务状态"""
    session = None
    try:
        username = request.args.get('username')
        
        session = get_local_session()
        task = TaskService.get_task(session, task_id)
        
        if not task:
            return jsonify({"error": "任务不存在", "message": f"任务 {task_id} 不存在"}), 404
        
        if username and task.username != username:
            return jsonify({"error": "无权限", "message": "您没有权限查看此任务"}), 403
        
        return jsonify({"task": task.to_dict()}), 200
    
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return jsonify({"error": str(e), "message": f"查询任务状态失败: {e}"}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """列出用户任务"""
    session = None
    try:
        username = request.args.get('username')
        status = request.args.get('status')
        
        if not username:
            return jsonify({"error": "缺少用户名", "message": "请提供用户名参数"}), 400
        
        session = get_local_session()
        tasks = TaskService.list_tasks(session, username, status)
        
        return jsonify({"tasks": [task.to_dict() for task in tasks]}), 200
    
    except Exception as e:
        logger.error(f"列出任务失败: {e}")
        return jsonify({"error": str(e), "message": f"列出任务失败: {e}"}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/fetch/<task_id>', methods=['GET'])
def fetch_task_results(task_id: str):
    """获取任务结果文件"""
    session = None
    try:
        username = request.args.get('username')
        
        session = get_local_session()
        task = TaskService.get_task(session, task_id)
        
        if not task:
            return jsonify({"error": "任务不存在", "message": f"任务 {task_id} 不存在"}), 404
        
        if username and task.username != username:
            return jsonify({"error": "无权限", "message": "您没有权限查看此任务"}), 403
        
        if task.target == 'local':
            # 本地任务 - 直接打包
            zip_path = FileService.create_local_result_archive(task)
            if zip_path:
                return send_file(
                    zip_path,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f"{task_id}_results.zip"
                )
            else:
                return jsonify({"error": "创建归档失败"}), 500
        
        elif task.target == 'remote':
            # 远程任务 - 调用远程API
            try:
                logs_paths = json.loads(task.logs_path or '[]')
                results_paths = json.loads(task.results_path or '[]')
                fetch_paths = logs_paths + results_paths
                
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
                    import tempfile
                    from pathlib import Path
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
        
        return jsonify({"error": "不支持的任务类型"}), 400
    
    except Exception as e:
        logger.error(f"获取任务结果失败: {e}")
        return jsonify({"error": str(e), "message": f"获取任务结果失败: {e}"}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id: str):
    """取消任务"""
    session = None
    try:
        username = request.args.get('username')
        
        session = get_local_session()
        task = TaskService.get_task(session, task_id)
        
        if not task:
            return jsonify({"error": "任务不存在", "message": f"任务 {task_id} 不存在"}), 404
        
        if username and task.username != username:
            return jsonify({"error": "无权限", "message": "您没有权限取消此任务"}), 403
        
        if task.status in ['completed', 'failed', 'canceled']:
            return jsonify({
                "message": f"任务已是 {task.status} 状态",
                "status": task.status
            }), 400
        
        # 取消Slurm作业
        if task.slurm_job_id:
            if task.target in ['local', 'local-run']:
                success, message = LocalSlurmService.cancel_job(task.slurm_job_id)
                if not success:
                    logger.warning(f"取消本地 Slurm 作业失败: {message}")
            elif task.target == 'remote':
                success, message = RemoteSlurmService.cancel_job(task.slurm_job_id)
                if not success:
                    logger.warning(f"取消远程 Slurm 作业失败: {message}")
        
        # 更新任务状态
        TaskService.cancel_task(session, task)
        
        logger.info(f"任务已取消: {task_id}")
        return jsonify({"message": f"任务 {task_id} 已取消", "status": "canceled"}), 200
    
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        return jsonify({"error": str(e), "message": f"取消任务失败: {e}"}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/logs/<task_id>', methods=['GET'])
def get_task_logs(task_id: str):
    """获取任务执行日志"""
    session = None
    try:
        username = request.args.get('username')
        
        session = get_local_session()
        task = TaskService.get_task(session, task_id)
        
        if not task:
            return jsonify({"error": "任务不存在", "message": f"任务 {task_id} 不存在"}), 404
        
        if username and task.username != username:
            return jsonify({"error": "无权限", "message": "您没有权限查看此任务"}), 403
        
        if task.target in ['local', 'local-run']:
            # 本地任务
            stdout, stderr = FileService.read_local_logs(task)
            return jsonify({"task_id": task_id, "stdout": stdout, "stderr": stderr}), 200
        
        elif task.target == 'remote':
            # 远程任务
            logs_data = RemoteSlurmService.get_logs(task_id, task.username, task.workdir)
            if logs_data:
                return jsonify(logs_data), 200
            else:
                return jsonify({"error": "获取远程日志失败"}), 500
        
        return jsonify({"error": "不支持的任务类型"}), 400
    
    except Exception as e:
        logger.error(f"获取任务日志失败: {e}")
        return jsonify({"error": str(e), "message": f"获取任务日志失败: {e}"}), 500
    finally:
        if session:
            session.close()


@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    polling_service = get_polling_service()
    return jsonify({
        "status": "healthy",
        "service": "local_proxy",
        "timestamp": datetime.now().isoformat(),
        "polling_active": polling_service.is_running()
    }), 200


@api_bp.route('/', methods=['GET'])
def index():
    """API文档"""
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
            "GET /api/health - 健康检查"
        ]
    }), 200
