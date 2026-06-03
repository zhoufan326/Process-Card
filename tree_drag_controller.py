"""Treeview 拖拽交互组件。

提供 TreeDragController 类，将 Treeview 的拖拽排序、单击选择
等交互逻辑封装为独立的可复用组件。

用法:
    controller = TreeDragController(
        tree,
        is_draggable=lambda item: item.startswith("g") and "_" not in item,
        on_select=app._on_tree_select,
        on_move=app._on_move_group,
        set_status=app._set_status,
    )
"""

from typing import Callable, Optional


class TreeDragController:
    """控制 ttk.Treeview 的拖拽与选择交互。

    负责事件绑定、拖拽状态管理和视觉反馈（高亮）。
    业务逻辑通过回调函数委托给外部。

    ---
    iid 约定（重要）
    本组件依赖业务方通过 is_draggable 回调来判定哪些树节点可拖拽。
    业务方需确保可拖拽的节点 iid 符合以下格式，以便 _get_group_index
    能从 iid 中解析出索引：

        可拖拽节点:  iid = f"g{索引}"      如 "g0", "g12"
        不可拖拽节点: iid = f"g{gi}_r{ri}"  如 "g0_r0", "g2_r3"

    如果业务方使用不同的 iid 命名规则，需覆盖 is_draggable 回调。
    """

    def __init__(
        self,
        tree,
        *,
        is_draggable: Callable[[str], bool],
        on_select: Optional[Callable[[str], None]] = None,
        on_move: Optional[Callable[[int, int], None]] = None,
        set_status: Optional[Callable[[str], None]] = None,
    ):
        """
        参数:
            tree: ttk.Treeview 实例
            is_draggable: 接收 item_id，返回 True 表示该行可拖拽
            on_select: 单击/选中回调, 接收 item_id
            on_move: 拖拽交换回调, 接收 (src_index, tgt_index)
            set_status: 状态栏更新回调, 接收字符串
        """
        self._tree = tree
        self._is_draggable = is_draggable
        self._on_select = on_select
        self._on_move = on_move
        self._set_status = set_status

        self._drag_source_idx: Optional[int] = None
        self._drag_target_idx: Optional[int] = None
        self._drag_did_move: bool = False

        self._bind_events()

    # ── 事件绑定 ──────────────────────────────

    def _bind_events(self):
        self._tree.bind("<Button-1>", self._on_press)
        self._tree.bind("<B1-Motion>", self._on_drag_motion)
        self._tree.bind("<ButtonRelease-1>", self._on_release)

    # ── 工具方法 ──────────────────────────────

    @staticmethod
    def _get_group_index(item: str) -> Optional[int]:
        """从可拖拽节点的 iid 中解析出组索引。

        要求 iid 格式为 'g<数字>'，例如 'g0' -> 0, 'g12' -> 12。
        此方法应与 is_draggable 回调配合使用——只有通过 is_draggable
        校验的节点才会进入此解析逻辑。
        """
        if item and item.startswith("g"):
            try:
                return int(item[1:])
            except ValueError:
                return None
        return None

    # ── 事件处理 ──────────────────────────────

    def _on_press(self, event):
        """鼠标按下：记录源组索引。"""
        item = self._tree.identify_row(event.y)
        if not item or not self._is_draggable(item):
            self._drag_source_idx = None
            self._drag_did_move = False
            return
        idx = self._get_group_index(item)
        if idx is not None:
            self._drag_source_idx = idx
            self._drag_target_idx = None
            self._drag_did_move = False

    def _on_drag_motion(self, event):
        """拖拽移动：高亮目标组行。"""
        if self._drag_source_idx is None:
            return
        item = self._tree.identify_row(event.y)
        if not item or not self._is_draggable(item):
            return
        target_idx = self._get_group_index(item)
        if target_idx is None or target_idx == self._drag_source_idx:
            return
        if target_idx == self._drag_target_idx:
            return

        self._drag_did_move = True
        self._drag_target_idx = target_idx
        self._tree.selection_set(item)
        if self._set_status:
            self._set_status(
                f"拖拽组 [{self._drag_source_idx + 1}] → 目标 [{target_idx + 1}]"
            )

    def _on_release(self, event):
        """鼠标释放：拖拽则执行交换，否则触发选择。"""
        if not self._drag_did_move or self._drag_source_idx is None or self._drag_target_idx is None:
            self._clear_drag_state()
            item = self._tree.identify_row(event.y)
            if item and self._on_select:
                self._on_select(item)
            return

        src = self._drag_source_idx
        tgt = self._drag_target_idx

        if self._on_move:
            self._on_move(src, tgt)

        moved_iid = f"g{tgt}"
        self._tree.selection_set(moved_iid)
        self._tree.focus(moved_iid)

        self._clear_drag_state()

    def _clear_drag_state(self):
        self._drag_source_idx = None
        self._drag_target_idx = None
        self._drag_did_move = False
