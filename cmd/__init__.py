"""命令模块 - 导出所有 CLI 命令"""

from .whoami import cmd_whoami
from .submit import cmd_submit
from .status import cmd_status
from .list import cmd_list
from .fetch import cmd_fetch
from .cancel import cmd_cancel
from .local_run import cmd_local_run

__all__ = [
    'cmd_whoami',
    'cmd_submit',
    'cmd_status',
    'cmd_list',
    'cmd_fetch',
    'cmd_cancel',
    'cmd_local_run',
]
