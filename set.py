"""纯数据类定义。

TaskGroup 是工序组的不可变定义。
全局状态管理已迁移至 app_state.AppState。
"""

from dataclasses import dataclass, field


@dataclass
class TaskGroup:
    """单个工序组数据。"""
    bay: str = ""
    process: str = ""
    obj: str = ""
    requires: list[str] = field(default_factory=list)
    row_height: int | float | None = None
