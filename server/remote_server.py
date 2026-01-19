#!/usr/bin/env python3
"""
Remote Server - 远端任务执行服务器

只负责：
1. 接收任务执行请求
2. 执行任务命令
3. 接受轮询，返回任务执行状态
"""
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from threading import Thread
from queue import Queue

from flask import Flask, request, jsonify

from shared.config import REMOTE_SERVER_PORT
from shared.logger import get_logger

# 初始化日志
logger = get_logger("remote_server")

# 初始化 Flask 应用
app = Flask(__name__)

# 任务执行队列和状态缓存
task_queue = Queue()
task_status = {}  # task_id -> {status, started_at, completed_at, exit_code, stdout, stderr}


# ============ 工作线程 ============

def execute_task(task_info):
    """执行任务
    
    Args:
        task_info: {
            task_id, username, command, workdir, timeout, 
            archive_path, ...
        }
    """
    task_id = task_info['task_id']
    command = task_info['command']
    workdir = task_info.get('workdir', '.')
    timeout = int(task_info.get('time_limit', '1:00:00').split(':')[0]) * 3600  # 转换为秒
    
    task_status[task_id] = {
        'status': 'running',
        'started_at': datetime.now().isoformat(),
        'completed_at': None,
        'exit_code': None,
        'stdout': '',
        'stderr': ''
    }
    
    logger.info(f"开始执行任务: {task_id}")
    
    try:
        # 执行命令
        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        task_status[task_id].update({
            'status': 'completed' if result.returncode == 0 else 'failed',
            'completed_at': datetime.now().isoformat(),
            'exit_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        })
        
        logger.info(f"任务执行完成: {task_id} (exit_code={result.returncode})")
        
    except subprocess.TimeoutExpired:
        task_status[task_id].update({
            'status': 'failed',
            'completed_at': datetime.now().isoformat(),
            'exit_code': -1,
            'stderr': f'任务执行超时 (>{timeout}s)'
        })
        logger.error(f"任务执行超时: {task_id}")
        
    except Exception as e:
        task_status[task_id].update({
            'status': 'failed',
            'completed_at': datetime.now().isoformat(),
            'exit_code': -1,
            'stderr': str(e)
        })
        logger.error(f"任务执行失败: {task_id} - {e}")


def task_worker():
    """后台工作线程，处理任务队列"""
    while True:
        task_info = task_queue.get()
        if task_info is None:  # 退出信号
            break
        execute_task(task_info)


# 启动工作线程
worker_thread = Thread(target=task_worker, daemon=True)
worker_thread.start()


# ============ API 路由 ============

@app.route('/api/execute', methods=['POST'])
def execute():
    """
    提交任务执行请求
    
    请求体:
    {
        "task_id": str,
        "username": str,
        "command": str,
        "workdir": str,
        "time_limit": str,  # "HH:MM:SS"
        "archive_path": str,
        ...
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
        required_fields = ['task_id', 'command']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "error": f"缺少必要字段: {field}",
                    "message": f"缺少必要字段: {field}"
                }), 400
        
        task_id = data['task_id']
        
        # 检查任务是否已存在
        if task_id in task_status:
            return jsonify({
                "error": "任务已存在",
                "message": f"任务 {task_id} 已在执行队列中"
            }), 409
        
        # 将任务加入队列
        task_queue.put(data)
        task_status[task_id] = {'status': 'pending'}
        
        logger.info(f"任务已入队: {task_id}")
        
        return jsonify({
            "task_id": task_id,
            "message": f"任务 {task_id} 已提交执行"
        }), 200
        
    except Exception as e:
        logger.error(f"提交任务失败: {e}")
        return jsonify({
            "error": str(e),
            "message": f"提交任务失败: {e}"
        }), 500


@app.route('/api/status/<task_id>', methods=['GET'])
def get_status(task_id: str):
    """
    轮询任务状态
    
    参数:
        task_id: 任务ID
    
    返回:
    {
        "task_id": str,
        "status": str,  # pending, running, completed, failed
        "started_at": str,
        "completed_at": str,
        "exit_code": int,
        "stdout": str,
        "stderr": str
    }
    """
    if task_id not in task_status:
        return jsonify({
            "error": "任务不存在",
            "message": f"任务 {task_id} 不存在"
        }), 404
    
    status_info = task_status[task_id]
    
    return jsonify({
        "task_id": task_id,
        **status_info
    }), 200


@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    """
    列出所有任务状态
    
    返回:
    {
        "tasks": [
            {"task_id": str, "status": str, ...},
            ...
        ]
    }
    """
    tasks = []
    for task_id, status in task_status.items():
        tasks.append({
            "task_id": task_id,
            **status
        })
    
    return jsonify({
        "tasks": tasks
    }), 200


@app.route('/api/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id: str):
    """
    取消任务（仅支持 pending 状态）
    
    参数:
        task_id: 任务ID
    
    返回:
    {
        "message": str
    }
    """
    if task_id not in task_status:
        return jsonify({
            "error": "任务不存在",
            "message": f"任务 {task_id} 不存在"
        }), 404
    
    status = task_status[task_id].get('status')
    
    if status == 'pending':
        task_status[task_id]['status'] = 'canceled'
        logger.info(f"任务已取消: {task_id}")
        return jsonify({
            "message": f"任务 {task_id} 已取消"
        }), 200
    elif status in ['running', 'completed', 'failed', 'canceled']:
        return jsonify({
            "error": "无法取消",
            "message": f"任务状态为 {status}，无法取消"
        }), 400
    
    return jsonify({
        "message": f"任务 {task_id} 操作完成"
    }), 200

def terminate_task(task_id: str):
    """终止正在运行的任务（未实现）"""
    # 这里可以实现通过记录的进程ID来终止任务的逻辑
    pass


# ============ 健康检查 ============

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "service": "remote_server",
        "timestamp": datetime.now().isoformat(),
        "tasks": len(task_status)
    }), 200


@app.route('/', methods=['GET'])
def index():
    """根路径"""
    return jsonify({
        "service": "ailabber Remote Server",
        "version": "1.0.0",
        "endpoints": [
            "POST /api/execute - 提交任务执行",
            "GET /api/status/<task_id> - 轮询任务状态",
            "GET /api/tasks - 列出所有任务",
            "POST /api/cancel/<task_id> - 取消任务",
            "GET /health - 健康检查"
        ]
    }), 200


# ============ 主入口 ============

def main():
    """启动服务器"""
    logger.info(f"Remote Server 启动于端口 {REMOTE_SERVER_PORT}")
    app.run(
        host='0.0.0.0',
        port=REMOTE_SERVER_PORT,
        debug=False,
        threaded=True
    )


if __name__ == '__main__':
    main()
