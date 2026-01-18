#!/usr/bin/env python3
"""
数据库初始化工具 (ORM 版本)

使用 SQLAlchemy ORM 管理数据库

用法:
    ailabber-db init      # 初始化数据库
    ailabber-db reset     # 重置数据库(删除后重建)
    ailabber-db status    # 查看数据库状态
    ailabber-db migrate   # 运行迁移(预留)
"""
import sys
from pathlib import Path
from datetime import datetime

from sqlalchemy import inspect, text

from shared.config import LOCAL_DB_PATH, REMOTE_DB_PATH, DATA_DIR
from shared.database import (
    Base, get_local_engine, get_remote_engine,
    init_local_db, init_remote_db,
    UserModel, TaskModel, MessageLogModel,
    TaskExecutionModel, UserStatsModel,
    LOCAL_MODELS, REMOTE_MODELS
)


CURRENT_VERSION = 1


# ============ 数据库操作函数 ============

def init_database(db_type: str) -> bool:
    """初始化数据库"""
    try:
        if db_type == "local":
            engine = init_local_db()
            db_path = LOCAL_DB_PATH
            db_name = "Local Proxy DB"
        else:
            engine = init_remote_db()
            db_path = REMOTE_DB_PATH
            db_name = "Remote Server DB"
        
        print(f"✓ {db_name} 初始化完成: {db_path}")
        return True
    except Exception as e:
        print(f"✗ {db_name} 初始化失败: {e}")
        return False


def reset_database(db_type: str) -> bool:
    """重置数据库 (删除后重建)"""
    try:
        if db_type == "local":
            db_path = LOCAL_DB_PATH
            db_name = "Local Proxy DB"
        else:
            db_path = REMOTE_DB_PATH
            db_name = "Remote Server DB"
        
        if db_path.exists():
            db_path.unlink()
            print(f"  已删除旧数据库: {db_path}")
        
        return init_database(db_type)
    except Exception as e:
        print(f"✗ {db_name} 重置失败: {e}")
        return False


def get_db_status(db_type: str) -> dict:
    """获取数据库状态"""
    if db_type == "local":
        db_path = LOCAL_DB_PATH
        db_name = "Local Proxy DB"
        engine = get_local_engine()
        models = LOCAL_MODELS
    else:
        db_path = REMOTE_DB_PATH
        db_name = "Remote Server DB"
        engine = get_remote_engine()
        models = REMOTE_MODELS
    
    status = {
        "name": db_name,
        "path": str(db_path),
        "exists": db_path.exists(),
        "size": 0,
        "tables": [],
        "row_counts": {},
        "models": [m.__tablename__ for m in models]
    }
    
    if not db_path.exists():
        return status
    
    status["size"] = db_path.stat().st_size
    
    try:
        inspector = inspect(engine)
        status["tables"] = inspector.get_table_names()
        
        # 获取行数
        with engine.connect() as conn:
            for table in status["tables"]:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    status["row_counts"][table] = result.scalar()
                except:
                    status["row_counts"][table] = "错误"
    except Exception as e:
        status["error"] = str(e)
    
    return status


def print_status(status: dict):
    """打印数据库状态"""
    print(f"\n{'='*50}")
    print(f"数据库: {status['name']}")
    print(f"{'='*50}")
    print(f"路径: {status['path']}")
    print(f"存在: {'是' if status['exists'] else '否'}")
    
    if not status["exists"]:
        print("(数据库不存在，请运行 init 命令)")
        return
    
    print(f"大小: {status['size'] / 1024:.1f} KB")
    print(f"\nORM 模型: {', '.join(status['models'])}")
    print(f"\n表格 ({len(status['tables'])} 个):")
    
    for table in status["tables"]:
        if table.startswith("sqlite_"):
            continue
        count = status["row_counts"].get(table, "?")
        marker = "✓" if table in status["models"] else " "
        print(f"  {marker} {table}: {count} 行")


def show_model_info():
    """显示模型信息"""
    print("\n" + "="*50)
    print("ORM 模型定义")
    print("="*50)
    
    print("\n[Local Proxy 模型]")
    for model in LOCAL_MODELS:
        print(f"\n  {model.__name__} ({model.__tablename__})")
        mapper = inspect(model)
        for col in mapper.columns:
            nullable = "" if col.nullable else " NOT NULL"
            pk = " [PK]" if col.primary_key else ""
            print(f"    - {col.name}: {col.type}{nullable}{pk}")
    
    print("\n[Remote Server 模型]")
    for model in REMOTE_MODELS:
        print(f"\n  {model.__name__} ({model.__tablename__})")
        mapper = inspect(model)
        for col in mapper.columns:
            nullable = "" if col.nullable else " NOT NULL"
            pk = " [PK]" if col.primary_key else ""
            print(f"    - {col.name}: {col.type}{nullable}{pk}")


# ============ 命令处理 ============

def cmd_init():
    """初始化所有数据库"""
    print("初始化数据库 (ORM)...")
    print(f"数据目录: {DATA_DIR}\n")
    
    success = True
    success &= init_database("local")
    success &= init_database("remote")
    
    if success:
        print("\n✓ 所有数据库初始化完成")
    else:
        print("\n✗ 部分数据库初始化失败")
    
    return success


def cmd_reset():
    """重置所有数据库"""
    print("警告: 这将删除所有现有数据!")
    confirm = input("确认重置? (输入 'yes' 确认): ")
    
    if confirm.lower() != "yes":
        print("已取消")
        return False
    
    print("\n正在重置数据库...")
    
    success = True
    success &= reset_database("local")
    success &= reset_database("remote")
    
    if success:
        print("\n✓ 所有数据库重置完成")
    else:
        print("\n✗ 部分数据库重置失败")
    
    return success


def cmd_status():
    """显示数据库状态"""
    print(f"数据目录: {DATA_DIR}")
    
    local_status = get_db_status("local")
    remote_status = get_db_status("remote")
    
    print_status(local_status)
    print_status(remote_status)


def cmd_models():
    """显示 ORM 模型信息"""
    show_model_info()


def cmd_migrate():
    """运行数据库迁移"""
    print("迁移功能预留")


def cmd_help():
    """显示帮助"""
    print(__doc__)
    print("\n可用命令:")
    print("  init    - 初始化数据库")
    print("  reset   - 重置数据库 (删除后重建)")
    print("  status  - 查看数据库状态")
    print("  models  - 查看 ORM 模型定义")
    print("  migrate - 运行迁移 (预留)")
    print("  help    - 显示帮助")


# ============ 主函数 ============

COMMANDS = {
    "init": cmd_init,
    "reset": cmd_reset,
    "status": cmd_status,
    "models": cmd_models,
    "migrate": cmd_migrate,
    "help": cmd_help,
}


def main():
    if len(sys.argv) < 2:
        cmd_help()
        return
    
    command = sys.argv[1]
    
    if command in COMMANDS:
        COMMANDS[command]()
    else:
        print(f"未知命令: {command}")
        cmd_help()


if __name__ == "__main__":
    main()
