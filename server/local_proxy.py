#!/usr/bin/env python3
"""
Local Proxy Server - 本地代理服务器

接收 CLI 请求，管理任务队列，与远程服务器通信
"""
import os
import json
import zipfile
import tempfile
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, send_file

from shared.config import LOCAL_PROXY_PORT, REMOTE_SERVER_PORT
from shared.database import (
    init_local_db, 
    get_local_session, 
    TaskModel, 
    UserModel,
    MessageLogModel
)
from shared.logger import get_logger

# 初始化日志
logger = get_logger("local_proxy")

# 初始化 Flask 应用
app = Flask(__name__)

# 初始化数据库
init_local_db()


# ============ 辅助函数 ============

def create_upload_archive(upload_path: str, ignore_patterns: list[str]) -> tuple[str, str]:
    """
    创建上传文件的压缩包
    
    Args:
        upload_path: 上传目录路径
        ignore_patterns: 忽略的文件/目录列表
        
    Returns:
        (archive_path, archive_hash): 压缩包路径和哈希值
    """
    upload_dir = Path(upload_path)
    if not upload_dir.exists():
        raise FileNotFoundError(f"上传目录不存在: {upload_path}")
    
    # 创建临时压缩文件
    temp_dir = Path(tempfile.gettempdir()) / "ailabber_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    archive_path = temp_dir / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    # 将 ignore_patterns 转换为绝对路径集合
    ignore_set = set(Path(p).resolve() for p in ignore_patterns if p)
    
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in upload_dir.rglob('*'):
            # 检查是否应该忽略
            if file_path.resolve() in ignore_set:
                continue
            # 检查父目录是否在忽略列表
            should_ignore = False
            for parent in file_path.parents:
                if parent.resolve() in ignore_set:
                    should_ignore = True
                    break
            if should_ignore:
                continue
            
            if file_path.is_file():
                arcname = file_path.relative_to(upload_dir)
                zf.write(file_path, arcname)
    
    # 计算哈希值
    with open(archive_path, 'rb') as f:
        archive_hash = hashlib.sha256(f.read()).hexdigest()[:16]
    
    return str(archive_path), archive_hash


def generate_msg_id() -> str:
    """生成消息 ID"""
    import uuid
    return str(uuid.uuid4())[:16]


# ============ API 路由 ============

@app.route('/api/submit', methods=['POST'])
def submit_task():
    """
    提交任务
    
    请求体:
    {
        "username": str,
        "pyproject_toml": str,
        "uv_lock": str,
        "extra_wheels": list[str],
        "upload": str,
        "ignore": list[str],
        "workdir": str,
        "commands": list[str],
        "logs": list[str],
        "results": list[str],
        "gpus": int,
        "cpus": int,
        "memory": str,
        "time_limit": str
    }
    
    返回:
    {
        "task_id": str,
        "message": str
    }
    """
    try:
        data = request.get_json()
        
        # 验证必要字段
        required_fields = ['username', 'upload', 'commands']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "error": f"缺少必要字段: {field}",
                    "message": f"缺少必要字段: {field}"
                }), 400
        
        username = data['username']
        upload_path = data['upload']
        ignore_patterns = data.get('ignore', [])
        
        # 创建上传压缩包
        try:
            archive_path, project_hash = create_upload_archive(upload_path, ignore_patterns)
        except FileNotFoundError as e:
            return jsonify({
                "error": str(e),
                "message": str(e)
            }), 400
        
        # 计算环境哈希（基于 pyproject.toml 和 uv.lock）
        env_content = f"{data.get('pyproject_toml', '')}:{data.get('uv_lock', '')}"
        env_hash = hashlib.sha256(env_content.encode()).hexdigest()[:16]
        
        # 生成任务 ID
        task_id = TaskModel.generate_id()
        
        # 合并命令
        commands = data.get('commands', [])
        command_str = ' && '.join(commands) if isinstance(commands, list) else commands
        
        # 创建任务记录
        session = get_local_session()
        try:
            task = TaskModel(
                task_id=task_id,
                username=username,
                name=data.get('name', f"task_{task_id}"),
                status="pending",
                command=command_str,
                gpus=data.get('gpus', 1),
                cpus=data.get('cpus', 4),
                memory=data.get('memory', '8G'),
                time_limit=data.get('time_limit', '1:00:00'),
                project_hash=project_hash,
                env_hash=env_hash,
            )
            session.add(task)
            
            # 更新用户统计
            user = session.query(UserModel).filter_by(username=username).first()
            if user:
                user.total_tasks += 1
            
            # 记录消息日志
            msg_log = MessageLogModel(
                msg_id=generate_msg_id(),
                msg_type="task_submit",
                direction="outgoing",
                payload=json.dumps({
                    "task_id": task_id,
                    "username": username,
                    "archive_path": archive_path,
                    "env_hash": env_hash,
                    "pyproject_toml": data.get('pyproject_toml'),
                    "uv_lock": data.get('uv_lock'),
                    "extra_wheels": data.get('extra_wheels', []),
                    "workdir": data.get('workdir', '.'),
                    "commands": commands,
                    "logs": data.get('logs', []),
                    "results": data.get('results', []),
                    "gpus": data.get('gpus', 1),
                    "cpus": data.get('cpus', 4),
                    "memory": data.get('memory', '8G'),
                    "time_limit": data.get('time_limit', '1:00:00')
                }),
                created_at=datetime.now()
            )
            session.add(msg_log)
            
            session.commit()
            
            logger.info(f"任务已提交: {task_id} (用户: {username})")
            
            # TODO: 发送任务到远程服务器
            # 这里需要实现与 remote_server 的通信逻辑
            
            return jsonify({
                "task_id": task_id,
                "message": f"任务 {task_id} 已成功提交"
            }), 200
            
        except Exception as e:
            session.rollback()
            logger.error(f"提交任务失败: {e}")
            return jsonify({
                "error": str(e),
                "message": f"提交任务失败: {e}"
            }), 500
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"处理请求失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"处理请求失败: {e}"
        }), 500


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
        limit: 数量限制 (query param, 可选, 默认50)
    
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
    limit = request.args.get('limit', 50, type=int)
    
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
        
        tasks = query.order_by(TaskModel.created_at.desc()).limit(limit).all()
        
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


@app.route('/api/logs/<task_id>', methods=['GET'])
def get_task_logs(task_id: str):
    """
    获取任务日志
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
    
    返回:
        日志文件压缩包 (zip)
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
                "message": "您没有权限访问此任务的日志"
            }), 403
        
        # TODO: 从远程服务器获取日志文件
        # 目前返回一个临时的日志压缩包
        
        # 创建临时日志文件
        temp_dir = Path(tempfile.gettempdir()) / "ailabber_logs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        log_zip_path = temp_dir / f"{task_id}_logs.zip"
        
        with zipfile.ZipFile(log_zip_path, 'w') as zf:
            # 添加日志内容
            log_content = task.logs or f"任务 {task_id} 的日志\n状态: {task.status}\n"
            zf.writestr(f"{task_id}_stdout.log", log_content)
            
            # 添加任务信息
            task_info = json.dumps(task.to_dict(), indent=2, ensure_ascii=False)
            zf.writestr(f"{task_id}_info.json", task_info)
        
        logger.info(f"下载任务日志: {task_id} (用户: {username})")
        
        return send_file(
            log_zip_path,
            as_attachment=True,
            download_name=f"{task_id}_logs.zip",
            mimetype='application/zip'
        )
        
    except Exception as e:
        logger.error(f"获取任务日志失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取任务日志失败: {e}"
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
        "status": str  # "canceled" 或 "terminated"
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
        
        # 检查任务状态
        old_status = task.status
        
        if task.status in ['completed', 'failed', 'canceled', 'terminated']:
            return jsonify({
                "message": f"任务已经是 {task.status} 状态，无法取消",
                "status": task.status
            }), 400
        
        # 根据任务状态决定操作
        if task.status == 'pending':
            # 未开始的任务直接取消
            task.status = 'canceled'
            new_status = 'canceled'
            message = f"任务 {task_id} 已取消"
        else:
            # 已开始的任务需要终止
            task.status = 'terminated'
            new_status = 'terminated'
            message = f"任务 {task_id} 已终止"
            
            # TODO: 发送取消请求到远程服务器
            # 需要实现与 remote_server 的通信来真正终止任务
        
        task.updated_at = datetime.now()
        
        # 记录消息日志
        msg_log = MessageLogModel(
            msg_id=generate_msg_id(),
            msg_type="task_cancel",
            direction="outgoing",
            payload=json.dumps({
                "task_id": task_id,
                "username": username,
                "old_status": old_status,
                "new_status": new_status
            }),
            created_at=datetime.now()
        )
        session.add(msg_log)
        
        session.commit()
        
        logger.info(f"任务状态变更: {task_id} {old_status} -> {new_status}")
        
        return jsonify({
            "message": message,
            "status": new_status
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


# ============ 健康检查 ============

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "service": "local_proxy",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def index():
    """根路径"""
    return jsonify({
        "service": "ailabber Local Proxy",
        "version": "1.0.0",
        "endpoints": [
            "POST /api/submit - 提交任务",
            "GET /api/status/<task_id> - 获取任务状态",
            "GET /api/tasks - 列出用户任务",
            "GET /api/logs/<task_id> - 下载任务日志",
            "POST /api/cancel/<task_id> - 取消任务",
            "GET /health - 健康检查"
        ]
    }), 200


# ============ 主入口 ============

def main():
    """启动服务器"""
    logger.info(f"Local Proxy 服务器启动于端口 {LOCAL_PROXY_PORT}")
    app.run(
        host='127.0.0.1',
        port=LOCAL_PROXY_PORT,
        debug=False,
        threaded=True
    )


if __name__ == '__main__':
    main()
