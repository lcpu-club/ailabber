"""Routes - Flask路由层"""
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file

from utils.logger import get_logger
from .services import SlurmService, FileService

logger = get_logger("remote_routes")

# 创建蓝图
api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/submit', methods=['POST'])
def submit():
    """提交 Slurm 作业"""
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
        
        # 提交作业
        success, result, message = SlurmService.submit_job(
            task_id=task_id,
            username=username,
            workdir=data.get('workdir', '.'),
            commands=commands,
            gpus=data.get('gpus', 0),
            cpus=data.get('cpus', 1),
            memory=data.get('memory', '4G'),
            time_limit=data.get('time_limit', '1:00:00'),
            partition=data.get('partition')
        )
        
        if success:
            return jsonify({
                "task_id": task_id,
                "slurm_job_id": result,
                "message": message
            }), 200
        else:
            return jsonify({
                "error": result,
                "task_id": task_id,
                "message": message
            }), 500
        
    except Exception as e:
        logger.error(f"提交任务异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"提交任务失败: {e}"
        }), 500


@api_bp.route('/status/<slurm_job_id>', methods=['GET'])
def get_status(slurm_job_id: str):
    """查询 Slurm 作业状态"""
    try:
        job_info = SlurmService.get_job_status(slurm_job_id)
        
        if job_info is None:
            return jsonify({
                "error": "作业不存在或查询失败",
                "message": f"无法获取作业 {slurm_job_id} 的状态"
            }), 404
        
        return jsonify({
            "slurm_job_id": slurm_job_id,
            "slurm_state": job_info.state,
            "status": SlurmService.map_job_state(job_info.state),
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


@api_bp.route('/logs/<task_id>', methods=['GET'])
def get_logs(task_id: str):
    """获取任务日志"""
    try:
        username = request.args.get('username')
        workdir = request.args.get('workdir', '.')
        
        if not username:
            return jsonify({
                "error": "缺少 username 参数",
                "message": "请提供 username 参数"
            }), 400
        
        stdout, stderr = FileService.read_logs(task_id, username, workdir)
        
        return jsonify({
            "task_id": task_id,
            "stdout": stdout,
            "stderr": stderr
        }), 200
        
    except Exception as e:
        logger.error(f"获取日志异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取日志失败: {e}"
        }), 500


@api_bp.route('/fetch/<task_id>', methods=['GET'])
def fetch_results(task_id: str):
    """获取任务结果文件（打包下载）"""
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
        
        zip_path = FileService.create_result_archive(
            task_id=task_id,
            username=username,
            workdir=workdir,
            fetch_paths=fetch_paths
        )
        
        if zip_path:
            logger.info(f"打包结果文件: {zip_path}")
            return send_file(
                zip_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{task_id}_results.zip"
            )
        else:
            return jsonify({
                "error": "创建归档失败",
                "message": "无法创建结果归档文件"
            }), 500
        
    except Exception as e:
        logger.error(f"获取结果异常: {e}")
        return jsonify({
            "error": str(e),
            "message": f"获取结果失败: {e}"
        }), 500


@api_bp.route('/cancel/<slurm_job_id>', methods=['POST'])
def cancel(slurm_job_id: str):
    """取消 Slurm 作业"""
    try:
        success, message = SlurmService.cancel_job(slurm_job_id)
        
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


@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "service": "remote_server",
        "timestamp": datetime.now().isoformat()
    }), 200


@api_bp.route('/', methods=['GET'])
def index():
    """API文档"""
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
            "GET /api/health - 健康检查"
        ]
    }), 200
