"""Edición tipo Excel sobre un Treeview (doble clic; combos de maestros)."""

from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

from ui.searchable_dropdown import SearchableDropdown
from ui.widgets import Theme


class TreeExcelEditor:
    def __init__(
        self,
        tree: ttk.Treeview,
        col_keys: tuple[str, ...],
        editables: set[str],
        *,
        combo_cols: Optional[set[str]] = None,
        on_change: Optional[Callable[[str, str, str], None]] = None,
        normalize: Optional[Callable[[str, str], str]] = None,
        can_edit: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self.tree = tree
        self.col_keys = col_keys
        self.editables = editables
        self.combo_cols = combo_cols or set()
        self.combo_values: dict[str, list[str]] = {}
        self.on_change = on_change
        self.normalize = normalize
        self.can_edit = can_edit
        self.dirty: set[str] = set()
        self._edit: Optional[tuple[str, str, tk.Widget]] = None
        self._focus_job: Optional[str] = None
        tree.bind("<Double-1>", self.begin_edit, add="+")
        tree.tag_configure("saved", background=Theme.ROW_SAVED, foreground=Theme.FG)
        tree.tag_configure("dirty", background=Theme.ROW_DIRTY, foreground=Theme.FG)

    def set_combo_values(self, values: dict[str, list[str]]) -> None:
        self.combo_values = {k: list(v) for k, v in values.items()}

    def commit(self) -> None:
        self._cancel_focus_job()
        if self._edit is None:
            return
        iid, key, widget = self._edit
        if isinstance(widget, SearchableDropdown):
            texto = widget.resolved_value()
        else:
            texto = widget.get().strip()  # type: ignore[attr-defined]
        self._edit = None
        widget.destroy()
        if not self.tree.exists(iid):
            return
        if self.normalize:
            texto = self.normalize(key, texto)
        self.tree.set(iid, key, texto)
        self.mark_dirty(iid)
        if self.on_change:
            self.on_change(iid, key, texto)

    def cancel(self) -> None:
        self._cancel_focus_job()
        if self._edit is None:
            return
        _iid, _key, widget = self._edit
        self._edit = None
        widget.destroy()

    def mark_dirty(self, iid: str) -> None:
        self.dirty.add(iid)
        tags = list(self.tree.item(iid, "tags") or ())
        tags = [t for t in tags if t not in ("saved", "dirty")]
        tags.append("dirty")
        self.tree.item(iid, tags=tuple(tags))

    def mark_saved(self, iid: str) -> None:
        self.dirty.discard(iid)
        tags = list(self.tree.item(iid, "tags") or ())
        tags = [t for t in tags if t not in ("saved", "dirty")]
        tags.append("saved")
        self.tree.item(iid, tags=tuple(tags))

    def clear(self) -> None:
        self.cancel()
        self.dirty.clear()

    def begin_edit(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        key = self._key(col)
        if not iid or key not in self.editables:
            return
        if self.can_edit and not self.can_edit(iid, key):
            return
        bbox = self.tree.bbox(iid, col)
        if not bbox:
            return
        self.commit()
        x, y, w, h = bbox
        actual = str(self.tree.set(iid, key))
        if actual in ("—", "…"):
            actual = ""
        widget: tk.Widget
        if key in self.combo_cols:
            widget = self._place_combo(x, y, w, h, key, actual)
        else:
            widget = self._place_entry(x, y, w, h, actual)
        self._edit = (iid, key, widget)
        widget.focus_set()
        widget.bind("<Escape>", lambda _e: self.cancel())
        widget.bind("<FocusOut>", self._on_focus_out)
        if isinstance(widget, SearchableDropdown):
            widget.open()
        else:
            widget.bind("<Return>", lambda _e: self.commit())

    def _place_entry(self, x: int, y: int, w: int, h: int, actual: str) -> tk.Entry:
        ent = tk.Entry(
            self.tree,
            font=("Segoe UI", 10),
            fg=Theme.FG,
            bg=Theme.ROW_DIRTY,
            relief=tk.SOLID,
            bd=1,
        )
        ent.place(x=x, y=y, width=w, height=h)
        ent.insert(0, actual)
        ent.select_range(0, tk.END)
        return ent

    def _place_combo(
        self, x: int, y: int, w: int, h: int, key: str, actual: str
    ) -> SearchableDropdown:
        valores = list(self.combo_values.get(key, ()))
        if actual and actual not in valores:
            valores = [actual] + valores
        dd = SearchableDropdown(
            self.tree,
            values=valores,
            width=12,
            font=("Segoe UI", 10),
            on_commit=lambda _v: self.commit(),
            compact=True,
        )
        dd.set(actual)
        dd.place(x=x, y=y, width=max(w, 130), height=max(h, 24))
        return dd

    def _on_focus_out(self, _event=None) -> None:
        self._cancel_focus_job()
        self._focus_job = self.tree.after(180, self._commit_if_left)

    def _commit_if_left(self) -> None:
        self._focus_job = None
        if self._edit is None:
            return
        widget = self._edit[2]
        fg = widget.focus_get()
        if fg is widget:
            return
        if isinstance(widget, SearchableDropdown) and widget.owns_widget(fg):
            return
        self.commit()

    def _cancel_focus_job(self) -> None:
        if self._focus_job is not None:
            try:
                self.tree.after_cancel(self._focus_job)
            except tk.TclError:
                pass
            self._focus_job = None

    def _key(self, col_id: str) -> str:
        idx = int(col_id.replace("#", "") or "1") - 1
        return self.col_keys[idx] if 0 <= idx < len(self.col_keys) else ""
