"""日志配置"""
import logging
import sys
from pathlib import Path
from core.config import LOG_LEVEL_CONSOLE, LOG_LEVEL_FILE, DATA_DIR

def get_logger(name: str) -> logging.Logger:
    """获取配置好的 logger"""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        # 设置日志处理器
        console_handler = logging.StreamHandler(sys.stderr)  # 输出到标准错误
        console_handler.setLevel(LOG_LEVEL_CONSOLE)
        
        # 日志文件放在数据目录下
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
        file_handler.setLevel(LOG_LEVEL_FILE)

        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)  # 设置为最低级别，具体输出由处理器控制
    
    return logger
