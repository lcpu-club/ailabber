#!/usr/bin/env python3
"""
Remote Server - 远端 Slurm 执行服务器

只负责：
1. 接收任务提交请求 -> 生成 Slurm 脚本并提交
2. 接受轮询 -> 返回 Slurm 作业状态
3. 返回日志和输出文件
"""
import os
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, send_file

from shared.config import REMOTE_SERVER_PORT, REMOTE_BASE_DIR
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
logger = get_logger("remote_server")

# 初始化 Flask 应用
app = Flask(__name__)


# ============ API 路由 ============

@app.route('/api/submit', methods=['POST'])
def submit():
    """
    提交 Slurm 作业
    
    请求体:
    {
        "task_id": str,
        "username": str,
        "workdir": str,          # 相对于用户目录的工作目录
        "commands": list[str],
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
        "message": str
    }
    """
    try:
        data = request.get_json()
        
        # 验证必要字段
        required_fields = ['task_id', 'username', 'commands']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "error": f"缺少必要字段: {field}",
                    "message": f"缺少必要字段: {field}"
                }), 400
        
        task_id = data['task_id']
        username = data['username']
        commands = data['commands']
        
        # 确定工作目录 (用户目录下)
        user_base = Path(REMOTE_BASE_DIR) / username
        workdir = data.get('workdir', '.')
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
            gpus=data.get('gpus', 0),
            cpus=data.get('cpus', 1),
            memory=data.get('memory', '4G'),
            time_limit=data.get('time_limit', '1:00:00'),
            output_file=output_file,
            error_file=error_file,
            partition=data.get('partition')
        )
        
        # 写入脚本文件
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        logger.info(f"生成 Slurm 脚本: {script_file}")
        
        # 提交 Slurm 作业
        success, result, stdout = submit_slurm_job(script_file)
        
        if success:
            slurm_job_id = result
            logger.info(f"Slurm 作业提交成功: task={task_id}, job={slurm_job_id}")
            
            return jsonify({
                "task_id": task_id,
                "slurm_job_id": slurm_job_id,
                "message": f"Slurm 作业提交成功: {slurm_job_id}"
            }), 200
        else:
            logger.error(f"Slurm 作业提交失败: task={task_id}, error={result}")
            return jsonify({
                "error": result,
                "task_id": task_id,
                "message": f"Slurm 提交失败: {result}"
            }), 500
        
    except Exception as e:
        logger.error(f"提交任务异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"提交任务失败: {e}"
        }), 500


@app.route('/api/status/<slurm_job_id>', methods=['GET'])
def get_status(slurm_job_id: str):
    """
    查询 Slurm 作业状态
    
    参数:
        slurm_job_id: Slurm 作业ID
    
    返回:
    {
        "slurm_job_id": str,
        "slurm_state": str,    # 原始 Slurm 状态
        "status": str,         # 统一状态 (pending, running, completed, failed, canceled)
        "exit_code": int,
        "node": str,
        "start_time": str,
        "end_time": str
    }
    """
    try:
        job_info = get_slurm_job_status(slurm_job_id)
        
        if job_info is None:
            return jsonify({
                "error": "作业不存在或查询失败",
                "message": f"无法获取作业 {slurm_job_id} 的状态"
            }), 404
        
        return jsonify({
            "slurm_job_id": slurm_job_id,
            "slurm_state": job_info.state,
            "status": map_slurm_state(job_info.state),
            "exit_code": job_info.exit_code,
            "node": job_info.node,
            "start_time": job_info.start_time,
            "end_time": job_info.end_time
        }), 200
        
    except Exception as e:
        logger.error(f"查询状态异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"查询状态失败: {e}"
        }), 500


@app.route('/api/logs/<task_id>', methods=['GET'])
def get_logs(task_id: str):
    """
    获取任务日志
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
        workdir: 工作目录 (query param, 可选)
    
    返回:
    {
        "task_id": str,
        "stdout": str,
        "stderr": str
    }
    """
    try:
        username = request.args.get('username')
        workdir = request.args.get('workdir', '.')
        
        if not username:
            return jsonify({
                "error": "缺少 username 参数",
                "message": "请提供 username 参数"
            }), 400
        
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
        
        return jsonify({
            "task_id": task_id,
            "stdout": stdout_content,
            "stderr": stderr_content
        }), 200
        
    except Exception as e:
        logger.error(f"获取日志异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取日志失败: {e}"
        }), 500


@app.route('/api/fetch/<task_id>', methods=['GET'])
def fetch_results(task_id: str):
    """
    获取任务结果文件（打包下载）
    
    参数:
        task_id: 任务ID
        username: 用户名 (query param)
        workdir: 工作目录 (query param)
        paths: 要获取的文件/目录列表 (query param, JSON 数组)
    
    返回:
        ZIP 压缩包
    """
    try:
        username = request.args.get('username')
        workdir = request.args.get('workdir', '.')
        paths_json = request.args.get('paths', '[]')
        
        if not username:
            return jsonify({
                "error": "缺少 username 参数",
                "message": "请提供 username 参数"
            }), 400
        
        try:
            fetch_paths = json.loads(paths_json)
        except json.JSONDecodeError:
            fetch_paths = []
        
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
        
        logger.info(f"打包结果文件: {zip_path}")
        
        return send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{task_id}_results.zip"
        )
        
    except Exception as e:
        logger.error(f"获取结果异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取结果失败: {e}"
        }), 500


@app.route('/api/cancel/<slurm_job_id>', methods=['POST'])
def cancel(slurm_job_id: str):
    """
    取消 Slurm 作业
    
    参数:
        slurm_job_id: Slurm 作业ID
    
    返回:
    {
        "slurm_job_id": str,
        "message": str
    }
    """
    try:
        success, message = cancel_slurm_job(slurm_job_id)
        
        if success:
            return jsonify({
                "slurm_job_id": slurm_job_id,
                "message": message
            }), 200
        else:
            return jsonify({
                "error": message,
                "slurm_job_id": slurm_job_id,
                "message": f"取消失败: {message}"
            }), 500
            
    except Exception as e:
        logger.error(f"取消作业异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"取消作业失败: {e}"
        }), 500


# ============ 健康检查 ============

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "service": "remote_server",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def index():
    """根路径 - API 文档"""
    return jsonify({
        "service": "ailabber Remote Server",
        "version": "2.0.0",
        "description": "远程 Slurm 作业管理服务",
        "endpoints": [
            "POST /api/submit - 提交 Slurm 作业",
            "GET /api/status/<slurm_job_id> - 查询作业状态",
            "GET /api/logs/<task_id>?username=&workdir= - 获取日志",
            "GET /api/fetch/<task_id>?username=&workdir=&paths= - 下载结果",
            "POST /api/cancel/<slurm_job_id> - 取消作业",
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
