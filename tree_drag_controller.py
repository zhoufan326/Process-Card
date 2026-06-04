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

    支持组级拖拽(gX)和组内 req 拖拽(gX_rY)。
    通过回调 on_move_group / on_move_req 委托业务逻辑。
    """

    def __init__(
        self,
        tree,
        *,
        is_draggable: Callable[[str], bool],
        on_select: Optional[Callable[[str], None]] = None,
        on_move_group: Optional[Callable[[int, int], None]] = None,
        on_move_req: Optional[Callable[[int, int, int], None]] = None,
        set_status: Optional[Callable[[str], None]] = None,
    ):
        """
        参数:
            tree: ttk.Treeview 实例
            is_draggable: 接收 item_id，返回 True 表示该行可拖拽
            on_select: 单击/选中回调, 接收 item_id
            on_move_group: 组交换回调, 接收 (src_index, tgt_index)
            on_move_req: 组内要求重排回调, 接收 (group_idx, src_req_idx, tgt_req_idx)
            set_status: 状态栏更新回调, 接收字符串
        """
        self._tree = tree
        self._is_draggable = is_draggable
        self._on_select = on_select
        self._on_move_group = on_move_group
        self._on_move_req = on_move_req
        self._set_status = set_status

        self._drag_src_item: Optional[str] = None
        self._drag_tgt_item: Optional[str] = None
        self._drag_did_move: bool = False

        self._bind_events()

    # ── 事件绑定 ──────────────────────────────

    def _bind_events(self):
        self._tree.bind("<Button-1>", self._on_press)
        self._tree.bind("<B1-Motion>", self._on_drag_motion)
        self._tree.bind("<ButtonRelease-1>", self._on_release)

    # ── 解析 iid ──────────────────────────────

    @staticmethod
    def _parse(item: str):
        """返回 (group_index, req_index_or_None)。
        如 "g3" -> (3, None); "g2_r5" -> (2, 5)。
        """
        if not item or not item.startswith("g"):
            return None, None
        parts = item.split("_")
        try:
            gi = int(parts[0][1:])
        except ValueError:
            return None, None
        ri = None
        if len(parts) == 2 and parts[1].startswith("r"):
            try:
                ri = int(parts[1][1:])
            except ValueError:
                pass
        return gi, ri

    def _can_drag(self, item: str) -> bool:
        if not item:
            return False
        if not self._is_draggable(item):
            return False
        gi, ri = self._parse(item)
        if gi is None:
            return False
        if ri is not None and self._get_group_size(gi) < 2:
            return False
        return True

    def _get_group_size(self, gi: int) -> int:
        children = self._tree.get_children(f"g{gi}")
        return len(children)

    # ── 事件处理 ──────────────────────────────

    def _on_press(self, event):
        item = self._tree.identify_row(event.y)
        if not self._can_drag(item):
            self._drag_src_item = None
            self._drag_did_move = False
            return
        self._drag_src_item = item
        self._drag_tgt_item = None
        self._drag_did_move = False

    def _on_drag_motion(self, event):
        if self._drag_src_item is None:
            return
        item = self._tree.identify_row(event.y)
        if not self._can_drag(item) or item == self._drag_src_item:
            return
        if item == self._drag_tgt_item:
            return

        self._drag_did_move = True
        self._drag_tgt_item = item
        self._tree.selection_set(item)

        s_gi, s_ri = self._parse(self._drag_src_item)
        t_gi, t_ri = self._parse(item)
        if s_ri is None and t_ri is None:
            msg = f"拖拽组 [{s_gi + 1}] → 目标 [{t_gi + 1}]"
        elif s_ri is not None and t_ri is not None and s_gi == t_gi:
            msg = f"拖拽要求 [{s_gi + 1}.{s_ri + 1}] → 目标 [{t_gi + 1}.{t_ri + 1}]"
        else:
            if self._set_status:
                self._set_status(f"不允许跨类型拖拽")
            self._drag_did_move = False
            return
        if self._set_status:
            self._set_status(msg)

    def _on_release(self, event):
        if not self._drag_did_move or self._drag_src_item is None or self._drag_tgt_item is None:
            self._clear()
            item = self._tree.identify_row(event.y)
            if item and self._on_select:
                self._on_select(item)
            return

        s_gi, s_ri = self._parse(self._drag_src_item)
        t_gi, t_ri = self._parse(self._drag_tgt_item)

        if s_ri is None and t_ri is None:
            if self._on_move_group:
                self._on_move_group(s_gi, t_gi)
            self._tree.selection_set(f"g{t_gi}")
        elif s_ri is not None and t_ri is not None and s_gi == t_gi:
            if self._on_move_req:
                self._on_move_req(s_gi, s_ri, t_ri)
            self._tree.selection_set(self._drag_tgt_item)

        self._clear()

    def _clear(self):
        self._drag_src_item = None
        self._drag_tgt_item = None
        self._drag_did_move = False
