import random
import re
from collections import defaultdict

from aqt import mw

from .i18n import t
from aqt.qt import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QEvent, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QStackedWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, Qt,
)

# ── Defaults (user can override in launcher) ─────────────────────────────────
DEFAULT_NOTE_TYPE = "MCQ-NB"

FLAG_DEFS = [
    (1, "Red",       "#ef4444"),
    (2, "Orange",    "#f97316"),
    (3, "Green",     "#22c55e"),
    (4, "Blue",      "#3b82f6"),
    (5, "Pink",      "#ec4899"),
    (6, "Turquoise", "#06b6d4"),
    (7, "Purple",    "#a855f7"),
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_note(note, note_type_name):
    """Parse a note into a structured dict. Returns None if invalid."""
    try:
        question = _strip_html(note["Question"].strip())
        if not question:
            return None
        options = {}
        for letter, field in [
            ("A", "option_1 (A)"), ("B", "option_2 (B)"),
            ("C", "option_3 (C)"), ("D", "option_4 (D)"),
            ("E", "option_5 (E)"),
        ]:
            try:
                val = _strip_html(note[field].strip())
                if val:
                    options[letter] = val
            except Exception:
                pass
        if not options:
            return None
        raw_ans = note["Ans"].strip().upper()
        correct = set()
        for ch in raw_ans:
            if ch in "ABCDE":
                correct.add(ch)
            elif ch in "12345":
                correct.add(chr(ord("A") + int(ch) - 1))
        correct = correct & set(options.keys())
        if not correct:
            return None
        source = ""
        try:
            source = _strip_html(note["Source"].strip())
        except Exception:
            pass
        explanation = ""
        try:
            explanation = note["Explanation"].strip()   # keep HTML for rendering
        except Exception:
            pass
        return {
            "question":    question,
            "options":     options,
            "correct":     sorted(correct),
            "source":      source,
            "explanation": explanation,
        }
    except Exception:
        return None


def _smart_sample(note_ids_with_meta, limit):
    """
    Round-robin across sub-decks so every lesson gets represented.
    Membership is balanced; ordering is preserved unless shuffle is applied later.
    note_ids_with_meta: list of (nid, meta_dict)
    Returns a list of nids of length `limit`.
    """
    groups = defaultdict(list)
    for nid, meta in note_ids_with_meta:
        groups[meta["deck"]].append(nid)
    buckets = list(groups.values())
    result = []
    # One question from each deck per round, so an emptied deck never makes
    # the rotation skip the next one.
    while len(result) < limit and any(buckets):
        for bucket in buckets:
            if bucket and len(result) < limit:
                result.append(bucket.pop(0))
    return result


# ── Card Picker Dialog ────────────────────────────────────────────────────────

class CardPickerDialog(QDialog):
    def __init__(self, parent, note_type_name):
        super().__init__(parent)
        self.note_type_name = note_type_name
        self.setWindowTitle(t("picker_title"))
        self.resize(1060, 680)
        self.setMinimumSize(800, 500)

        self._note_meta       = {}   # nid -> {deck, tags, flag, preview}
        self._all_note_ids    = []
        self._selected        = set()
        self._active_deck     = None
        self._active_tags     = set()
        self._active_exam_tags = set()
        self._active_flags    = set()
        self._history_index   = {}

        self._build_ui()
        self._load_all_notes()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(h_splitter, 1)

        # ── LEFT panel: native filter list + one active panel ───────────────
        left = QWidget()
        left.setMinimumWidth(260)
        left.setMaximumWidth(340)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 4, 4)
        lv.setSpacing(6)

        nav_row = QVBoxLayout()
        nav_row.setSpacing(4)
        self._filter_buttons = QButtonGroup(self)
        self._filter_buttons.setExclusive(True)
        self._filter_stack = QStackedWidget()

        # Deck panel
        deck_widget = QWidget()
        dv = QVBoxLayout(deck_widget)
        dv.setContentsMargins(8, 8, 8, 8)
        dv.setSpacing(6)
        deck_lbl = QLabel(t("browse_decks"))
        deck_lbl.setStyleSheet("font-weight:bold;font-size:13px;")
        dv.addWidget(deck_lbl)
        self.deck_tree = QTreeWidget()
        self.deck_tree.setHeaderHidden(True)
        self.deck_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.deck_tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.deck_tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.deck_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.deck_tree.itemSelectionChanged.connect(self._on_deck_changed)
        dv.addWidget(self.deck_tree)
        self._filter_stack.addWidget(deck_widget)

        # Tags panel
        tag_widget = QWidget()
        tv = QVBoxLayout(tag_widget)
        tv.setContentsMargins(8, 8, 8, 8)
        tv.setSpacing(6)
        tag_lbl = QLabel(t("tags"))
        tag_lbl.setStyleSheet("font-weight:bold;font-size:13px;")
        tv.addWidget(tag_lbl)
        self.tag_list = QListWidget()
        self.tag_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.tag_list.setStyleSheet(
            "QListWidget::item { padding: 5px 6px; }"
            "QListWidget::indicator { width: 20px; height: 20px; }"
        )
        self.tag_list.itemChanged.connect(self._on_tag_changed)
        self.tag_list.viewport().installEventFilter(self)
        tv.addWidget(self.tag_list)
        self._filter_stack.addWidget(tag_widget)

        # Simulation History panel
        exam_tag_widget = QWidget()
        etv = QVBoxLayout(exam_tag_widget)
        etv.setContentsMargins(8, 8, 8, 8)
        etv.setSpacing(6)
        exam_tag_lbl = QLabel(t("simulation_history"))
        exam_tag_lbl.setStyleSheet("font-weight:bold;font-size:13px;")
        etv.addWidget(exam_tag_lbl)

        history_btn_row = QHBoxLayout()
        self.delete_history_btn = QPushButton(t("delete_selected"))
        self.clear_history_btn = QPushButton(t("clear_all"))
        self.delete_history_btn.clicked.connect(self._delete_selected_history)
        self.clear_history_btn.clicked.connect(self._clear_all_history)
        history_btn_row.addWidget(self.delete_history_btn)
        history_btn_row.addWidget(self.clear_history_btn)
        etv.addLayout(history_btn_row)

        self.exam_tag_list = QListWidget()
        self.exam_tag_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.exam_tag_list.setStyleSheet(
            "QListWidget::item { padding: 5px 6px; }"
            "QListWidget::indicator { width: 20px; height: 20px; }"
        )
        self.exam_tag_list.itemChanged.connect(self._on_exam_tag_changed)
        self.exam_tag_list.viewport().installEventFilter(self)
        etv.addWidget(self.exam_tag_list)
        self._filter_stack.addWidget(exam_tag_widget)

        # Flags panel
        flag_widget = QWidget()
        fv = QVBoxLayout(flag_widget)
        fv.setContentsMargins(8, 8, 8, 8)
        fv.setSpacing(6)
        flag_lbl = QLabel(t("flags"))
        flag_lbl.setStyleSheet("font-weight:bold;font-size:13px;")
        fv.addWidget(flag_lbl)
        self._flag_checks = {}
        for fnum, name, color in FLAG_DEFS:
            cb = QCheckBox(f"  {t(f'flag_{fnum}')}")
            cb.setStyleSheet(f"color:{color};font-weight:bold;font-size:12px;")
            cb.stateChanged.connect(self._on_flag_changed)
            self._flag_checks[fnum] = cb
            fv.addWidget(cb)
        fv.addStretch()
        self._filter_stack.addWidget(flag_widget)

        for idx, label in enumerate([t("decks"), t("tags"), t("simulation_history"), t("flags")]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.clicked.connect(lambda checked, i=idx: self._set_filter_panel(i))
            self._filter_buttons.addButton(btn, idx)
            nav_row.addWidget(btn)

        lv.addLayout(nav_row)
        lv.addWidget(self._filter_stack, 1)
        h_splitter.addWidget(left)

        # ── RIGHT panel: search + active filters + list ───────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setSpacing(6)
        rv.setContentsMargins(4, 4, 4, 4)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(t("search_placeholder"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._apply_filters)
        rv.addWidget(self.search_box)

        self._active_filters_wrap = QWidget()
        self._active_filters_layout = QHBoxLayout(self._active_filters_wrap)
        self._active_filters_layout.setContentsMargins(0, 0, 0, 0)
        self._active_filters_layout.setSpacing(6)
        rv.addWidget(self._active_filters_wrap)

        sel_row = QHBoxLayout()
        sel_all = QPushButton(t("select_all_visible"))
        sel_none = QPushButton(t("deselect_all_visible"))
        sel_all.clicked.connect(self._select_all_visible)
        sel_none.clicked.connect(self._deselect_visible)
        self.preview_btn = QPushButton(t("preview"))
        self.preview_btn.setCheckable(True)
        self.preview_btn.setToolTip(t("preview_tip"))
        self.preview_btn.toggled.connect(self._toggle_preview)
        self.visible_lbl = QLabel(t("n_shown", n=0))
        self.visible_lbl.setStyleSheet("color:#64748b;")
        self.count_lbl = QLabel(t("selected_count", n=0))
        self.count_lbl.setStyleSheet("font-weight:bold;color:#2563eb;")
        sel_row.addWidget(sel_all)
        sel_row.addWidget(sel_none)
        sel_row.addWidget(self.preview_btn)
        sel_row.addStretch()
        sel_row.addWidget(self.visible_lbl)
        sel_row.addWidget(self.count_lbl)
        rv.addLayout(sel_row)

        self._list_preview_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.result_list = QListWidget()
        self.result_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.result_list.setSpacing(2)
        self.result_list.setStyleSheet(
            "QListWidget::item { padding: 5px 6px; }"
            "QListWidget::indicator { width: 20px; height: 20px; }"
        )
        self.result_list.viewport().installEventFilter(self)
        self.result_list.itemChanged.connect(self._on_result_item_changed)
        self.result_list.currentItemChanged.connect(self._on_preview_item)
        self._list_preview_splitter.addWidget(self.result_list)

        self._preview_pane = QWidget()
        self._preview_pane.setMinimumWidth(280)
        self._preview_pane.setVisible(False)
        pv_outer = QVBoxLayout(self._preview_pane)
        pv_outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._preview_inner = QWidget()
        self._preview_layout = QVBoxLayout(self._preview_inner)
        self._preview_layout.setSpacing(6)
        self._preview_layout.setContentsMargins(14, 14, 14, 14)
        self._preview_layout.addStretch()
        scroll.setWidget(self._preview_inner)
        pv_outer.addWidget(scroll)
        self._list_preview_splitter.addWidget(self._preview_pane)
        self._list_preview_splitter.setSizes([700, 0])

        rv.addWidget(self._list_preview_splitter, 1)

        h_splitter.addWidget(right)
        h_splitter.setSizes([300, 760])

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton(t("cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(t("use_selected"))
        ok.setDefault(True)
        ok.clicked.connect(self._confirm)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        root.addLayout(btn_row)

        first_btn = self._filter_buttons.button(0)
        if first_btn:
            first_btn.setChecked(True)
        self._set_filter_panel(0)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_all_notes(self):
        query = f'note:"{self.note_type_name}"'
        try:
            nids = list(mw.col.find_notes(query))
        except Exception:
            nids = []
        self._all_note_ids = list(nids)

        from .history_store import grouped_history

        deck_set = set()
        tag_set = set()

        for nid in nids:
            note = mw.col.get_note(nid)
            parsed = _parse_note(note, self.note_type_name)
            if not parsed:
                continue
            cards = note.cards()
            deck_name = ""
            flag = 0
            if cards:
                try:
                    deck_name = mw.col.decks.name(cards[0].did)
                except Exception:
                    pass
                flag = cards[0].flags & 0x07
            tags = []
            for t in note.tags:
                tags.append(t)
                tag_set.add(t)
            deck_set.add(deck_name)
            preview_text = parsed["question"]
            preview = preview_text[:140] + ("…" if len(preview_text) > 140 else "")
            self._note_meta[nid] = {
                "deck":        deck_name,
                "tags":        tags,
                "flag":        flag,
                "preview":     preview,
                "search_text": preview_text.lower(),
            }

        self._history_index = {
            entry["label"]: set(entry["note_ids"])
            for entry in grouped_history()
        }

        self._populate_deck_tree(deck_set)
        self._populate_tag_list(tag_set)
        self._populate_exam_tag_list(self._history_index.keys())
        self._apply_filters()

    def _populate_deck_tree(self, deck_names):
        self.deck_tree.blockSignals(True)
        self.deck_tree.clear()
        all_item = QTreeWidgetItem([t("all_decks")])
        all_item.setData(0, Qt.ItemDataRole.UserRole, None)
        self.deck_tree.addTopLevelItem(all_item)
        nodes = {}
        for full_name in sorted(deck_names):
            if not full_name:
                continue
            parts = full_name.split("::")
            for depth in range(len(parts)):
                path = "::".join(parts[:depth + 1])
                if path in nodes:
                    continue
                item = QTreeWidgetItem([parts[depth]])
                item.setData(0, Qt.ItemDataRole.UserRole, path)
                if depth == 0:
                    self.deck_tree.addTopLevelItem(item)
                else:
                    parent_path = "::".join(parts[:depth])
                    nodes[parent_path].addChild(item)
                nodes[path] = item
        self.deck_tree.expandAll()
        self.deck_tree.resizeColumnToContents(0)
        self.deck_tree.setCurrentItem(all_item)
        self.deck_tree.blockSignals(False)

    def _populate_tag_list(self, tags):
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for tag in sorted(tags):
            if not tag:
                continue
            item = QListWidgetItem(tag)
            item.setData(Qt.ItemDataRole.UserRole, tag)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.tag_list.addItem(item)
        self.tag_list.blockSignals(False)

    def _populate_exam_tag_list(self, history_labels):
        previous = set(self._active_exam_tags)
        self.exam_tag_list.blockSignals(True)
        self.exam_tag_list.clear()
        for label in history_labels:
            if not label:
                continue
            item = QListWidgetItem(label)
            item.setToolTip(label)
            item.setData(Qt.ItemDataRole.UserRole, label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if label in previous else Qt.CheckState.Unchecked
            )
            self.exam_tag_list.addItem(item)
        self.exam_tag_list.blockSignals(False)
        self.delete_history_btn.setEnabled(self.exam_tag_list.count() > 0)
        self.clear_history_btn.setEnabled(self.exam_tag_list.count() > 0)

    # ── Filter handlers ───────────────────────────────────────────────────────

    def _on_deck_changed(self):
        sel = self.deck_tree.selectedItems()
        self._active_deck = sel[0].data(0, Qt.ItemDataRole.UserRole) if sel else None
        self._apply_filters()

    def _on_tag_changed(self):
        self._active_tags = set()
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self._active_tags.add(item.data(Qt.ItemDataRole.UserRole) or item.text())
        self._apply_filters()

    def _on_exam_tag_changed(self):
        self._active_exam_tags = set()
        for i in range(self.exam_tag_list.count()):
            item = self.exam_tag_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self._active_exam_tags.add(item.data(Qt.ItemDataRole.UserRole) or item.text())
        self._apply_filters()

    def _reload_history_index(self):
        from .history_store import grouped_history

        self._history_index = {
            entry["label"]: set(entry["note_ids"])
            for entry in grouped_history()
        }
        self._active_exam_tags &= set(self._history_index.keys())
        self._populate_exam_tag_list(self._history_index.keys())

    def _checked_history_labels(self):
        labels = []
        for i in range(self.exam_tag_list.count()):
            item = self.exam_tag_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                labels.append(item.data(Qt.ItemDataRole.UserRole) or item.text())
        return labels

    def _delete_selected_history(self):
        from .history_store import delete_history_labels

        labels = self._checked_history_labels()
        if not labels:
            QMessageBox.information(self, t("no_history_selected_title"),
                                    t("no_history_selected_msg"))
            return
        count = len(labels)
        answer = QMessageBox.question(
            self,
            t("delete_history_title"),
            t("delete_history_msg", n=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        delete_history_labels(labels)
        self._reload_history_index()
        self._apply_filters()

    def _clear_all_history(self):
        from .history_store import clear_history

        if not self._history_index:
            return
        answer = QMessageBox.question(
            self,
            t("clear_history_title"),
            t("clear_history_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        clear_history()
        self._active_exam_tags.clear()
        self._reload_history_index()
        self._apply_filters()

    def _set_filter_panel(self, index):
        self._filter_stack.setCurrentIndex(index)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if obj is self.result_list.viewport():
                item = self.result_list.itemAt(event.pos())
                if item is not None:
                    rect = self.result_list.visualItemRect(item)
                    indicator_zone = rect.left() + 28
                    if event.pos().x() > indicator_zone:
                        self.result_list.blockSignals(True)
                        new_state = (Qt.CheckState.Unchecked
                                     if item.checkState() == Qt.CheckState.Checked
                                     else Qt.CheckState.Checked)
                        item.setCheckState(new_state)
                        self.result_list.blockSignals(False)
                        self._on_result_item_changed(item)
                        self.result_list.setCurrentItem(item)
                        return True
            elif obj in (self.tag_list.viewport(), self.exam_tag_list.viewport()):
                list_widget = self.tag_list if obj is self.tag_list.viewport() else self.exam_tag_list
                item = list_widget.itemAt(event.pos())
                if item is not None:
                    rect = list_widget.visualItemRect(item)
                    indicator_zone = rect.left() + 28
                    if event.pos().x() > indicator_zone:
                        self._toggle_checkable_item(list_widget, item)
                        return True
        return super().eventFilter(obj, event)

    def _toggle_checkable_item(self, list_widget, item):
        list_widget.blockSignals(True)
        new_state = (Qt.CheckState.Unchecked
                     if item.checkState() == Qt.CheckState.Checked
                     else Qt.CheckState.Checked)
        item.setCheckState(new_state)
        list_widget.blockSignals(False)
        if list_widget is self.tag_list:
            self._on_tag_changed()
        elif list_widget is self.exam_tag_list:
            self._on_exam_tag_changed()

    def _clear_active_filter_chips(self):
        while self._active_filters_layout.count():
            item = self._active_filters_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _add_filter_chip(self, text):
        chip = QLabel(text)
        chip.setFrameShape(QFrame.Shape.Panel)
        chip.setFrameShadow(QFrame.Shadow.Raised)
        chip.setMargin(4)
        self._active_filters_layout.addWidget(chip)

    def _update_active_filter_chips(self):
        self._clear_active_filter_chips()
        added = False
        if self._active_deck:
            self._add_filter_chip(t("chip_deck", v=self._active_deck))
            added = True
        for tag in sorted(self._active_tags):
            self._add_filter_chip(t("chip_tag", v=tag))
            added = True
        for tag in sorted(self._active_exam_tags):
            display = tag.split("::", 1)[1] if "::" in tag else tag
            self._add_filter_chip(t("chip_simulation", v=display))
            added = True
        for fnum in sorted(self._active_flags):
            self._add_filter_chip(t("chip_flag", v=t(f"flag_{fnum}")))
            added = True
        search = self.search_box.text().strip()
        if search:
            self._add_filter_chip(t("chip_search", v=search))
            added = True
        if not added:
            empty = QLabel(t("no_filters"))
            self._active_filters_layout.addWidget(empty)
        self._active_filters_layout.addStretch()

    def _on_flag_changed(self):
        self._active_flags = {
            fnum for fnum, cb in self._flag_checks.items() if cb.isChecked()
        }
        self._apply_filters()

    def _note_matches(self, nid):
        meta   = self._note_meta[nid]
        search = self.search_box.text().lower()
        if self._active_deck:
            dn = meta["deck"]
            if dn != self._active_deck and not dn.startswith(
                    self._active_deck + "::"):
                return False
        if self._active_tags:
            if not (self._active_tags & set(meta["tags"])):
                return False
        if self._active_exam_tags:
            if not any(nid in self._history_index.get(history_name, set())
                       for history_name in self._active_exam_tags):
                return False
        if self._active_flags:
            if meta["flag"] not in self._active_flags:
                return False
        if search and search not in meta.get("search_text", meta["preview"].lower()):
            return False
        return True

    def _apply_filters(self):
        self._update_active_filter_chips()
        visible = [
            (nid, self._note_meta[nid])
            for nid in self._note_meta
            if self._note_matches(nid)
        ]
        visible.sort(key=lambda x: x[1]["preview"])
        self._rebuild_list(visible)

    def _result_item_label(self, nid, meta):
        flag_str = "[" + t("flag_%d" % meta["flag"]) + "] " if meta["flag"] > 0 else ""
        tag_str = ""
        if meta["tags"]:
            tag_str = "  🏷 " + ", ".join(meta["tags"][:3])
            if len(meta["tags"]) > 3:
                tag_str += "…"
        return f"{flag_str}{meta['preview']}   〔{meta['deck']}〕{tag_str}"

    def _sync_result_item(self, item):
        nid = item.data(Qt.ItemDataRole.UserRole)
        meta = self._note_meta.get(nid)
        if meta is None:
            return
        item.setText(self._result_item_label(nid, meta))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            Qt.CheckState.Checked if nid in self._selected else Qt.CheckState.Unchecked
        )

    def _rebuild_list(self, items):
        self.result_list.blockSignals(True)
        self.result_list.clear()
        for nid, meta in items:
            item = QListWidgetItem(self._result_item_label(nid, meta))
            item.setData(Qt.ItemDataRole.UserRole, nid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if nid in self._selected else Qt.CheckState.Unchecked
            )
            self.result_list.addItem(item)
        self.result_list.blockSignals(False)
        self.visible_lbl.setText(t("n_shown", n=len(items)))
        self._refresh_count()

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_result_item_changed(self, item):
        nid = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(nid)
        else:
            self._selected.discard(nid)
        self._refresh_count()

    def _select_all_visible(self):
        self.result_list.blockSignals(True)
        for i in range(self.result_list.count()):
            item = self.result_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)
            self._selected.add(item.data(Qt.ItemDataRole.UserRole))
        self.result_list.blockSignals(False)
        self._refresh_count()

    def _deselect_visible(self):
        """Only deselects currently visible rows — hidden selections preserved."""
        self.result_list.blockSignals(True)
        for i in range(self.result_list.count()):
            item = self.result_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._selected.discard(item.data(Qt.ItemDataRole.UserRole))
        self.result_list.blockSignals(False)
        self._refresh_count()

    def _refresh_count(self):
        self.count_lbl.setText(t("selected_count", n=len(self._selected)))

    def _toggle_preview(self, checked):
        self._preview_pane.setVisible(checked)
        if checked:
            self._list_preview_splitter.setSizes([420, 320])
            current = self.result_list.currentItem()
            if current:
                self._on_preview_item(current, None)
        else:
            self._list_preview_splitter.setSizes([700, 0])
            self._clear_preview()

    def _clear_preview(self):
        layout = self._preview_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_preview_item(self, current, previous):
        if not self._preview_pane.isVisible() or current is None:
            return
        nid = current.data(Qt.ItemDataRole.UserRole)
        if nid is None:
            return
        meta = self._note_meta.get(nid)
        if not meta:
            return

        try:
            note = mw.col.get_note(nid)
            q = _parse_note(note, self.note_type_name)
        except Exception:
            q = None

        self._clear_preview()
        layout = self._preview_layout

        def lbl(text, bold=False, size=13, italic=False, color=None):
            w = QLabel(text)
            w.setWordWrap(True)
            style = f"font-size:{size}px;"
            if bold:
                style += "font-weight:bold;"
            if italic:
                style += "font-style:italic;"
            if color:
                style += f"color:{color};"
            w.setStyleSheet(style)
            w.setTextFormat(Qt.TextFormat.PlainText)
            return w

        layout.insertWidget(layout.count() - 1, lbl(meta["deck"], size=11, italic=True))

        if meta["flag"] > 0:
            finfo = FLAG_DEFS[meta["flag"] - 1]
            layout.insertWidget(
                layout.count() - 1,
                lbl("⚑  " + t("flag_%d" % meta["flag"]), color=finfo[2], size=12, bold=True)
            )

        if meta["tags"]:
            layout.insertWidget(
                layout.count() - 1, lbl("  ·  ".join(meta["tags"]), size=11)
            )

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.insertWidget(layout.count() - 1, sep)

        if q:
            layout.insertWidget(
                layout.count() - 1, lbl(q["question"], bold=True, size=14)
            )
            for letter, text in q["options"].items():
                row = QWidget()
                rh = QHBoxLayout(row)
                rh.setContentsMargins(4, 0, 0, 0)
                rh.setSpacing(8)
                ll = QLabel(f"{letter}.")
                ll.setStyleSheet("font-weight:bold;font-size:13px;")
                ll.setFixedWidth(22)
                lt = QLabel(text)
                lt.setWordWrap(True)
                lt.setStyleSheet("font-size:13px;")
                lt.setTextFormat(Qt.TextFormat.PlainText)
                rh.addWidget(ll)
                rh.addWidget(lt, 1)
                layout.insertWidget(layout.count() - 1, row)
            if q.get("source"):
                src_w = QLabel(f"📚  {q['source']}")
                src_w.setWordWrap(True)
                src_w.setStyleSheet("font-size:11px;font-style:italic;")
                src_w.setTextFormat(Qt.TextFormat.PlainText)
                layout.insertWidget(layout.count() - 1, src_w)
        else:
            layout.insertWidget(
                layout.count() - 1, lbl(t("cannot_parse"), size=12)
            )

    def _confirm(self):
        if not self._selected:
            QMessageBox.warning(self, t("nothing_selected_title"),
                                t("nothing_selected_msg"))
            return
        self.accept()

    def selected_note_ids(self):
        return [nid for nid in self._all_note_ids if nid in self._selected]

    def note_meta(self):
        return self._note_meta


# ── Launcher Dialog ───────────────────────────────────────────────────────────

class LauncherDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(t("setup_title"))
        self.setMinimumWidth(480)
        self._picked_ids  = []
        self._picked_meta = {}   # nid -> meta (for smart sampling)
        self._note_type_names = []
        self._build_ui()

    def _populate_note_types(self):
        self._note_type_names = []
        try:
            models = mw.col.models.all()
            self._note_type_names = sorted(
                m.get("name", "") for m in models if m.get("name")
            )
        except Exception:
            self._note_type_names = [DEFAULT_NOTE_TYPE]

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._populate_note_types()

        # ── Note type ───────────────────────────────────────────────────────
        nt_group = QGroupBox(t("note_type"))
        nt_layout = QVBoxLayout(nt_group)
        nt_top = QHBoxLayout()
        nt_hint = QLabel(t("choose_note_type"))
        self.note_type_combo = QComboBox()
        self.note_type_combo.addItems(self._note_type_names)
        default_idx = self.note_type_combo.findText(DEFAULT_NOTE_TYPE)
        if default_idx >= 0:
            self.note_type_combo.setCurrentIndex(default_idx)
        self.note_type_combo.setToolTip(
            t("note_type_tip"))
        nt_top.addWidget(nt_hint)
        nt_top.addWidget(self.note_type_combo, 1)
        nt_layout.addLayout(nt_top)
        layout.addWidget(nt_group)

        # ── Exam name ───────────────────────────────────────────────────────
        name_group = QGroupBox(t("exam_name"))
        name_layout = QVBoxLayout(name_group)
        name_label = QLabel(t("simulation_name"))
        name_help = QLabel(t("saved_in_history"))
        name_help.setWordWrap(True)
        name_help.setStyleSheet("color:#64748b;font-size:12px;")
        self.exam_name_edit = QLineEdit()
        self.exam_name_edit.setPlaceholderText(t("exam_name_placeholder"))
        name_layout.addWidget(name_label)
        name_layout.addWidget(name_help)
        name_layout.addWidget(self.exam_name_edit)
        layout.addWidget(name_group)

        # ── Question selection ──────────────────────────────────────────────
        q_group = QGroupBox(t("questions"))
        q_layout = QVBoxLayout(q_group)

        pick_row = QHBoxLayout()
        self.pick_label = QLabel(t("none_selected_yet"))
        self.pick_label.setStyleSheet("color:#64748b;font-style:italic;")
        pick_btn = QPushButton(t("browse_pick"))
        pick_btn.clicked.connect(self._open_picker)
        pick_row.addWidget(self.pick_label, 1)
        pick_row.addWidget(pick_btn)
        q_layout.addLayout(pick_row)

        limit_row = QHBoxLayout()
        self.limit_check = QCheckBox(t("limit_to"))
        self.limit_spin  = QSpinBox()
        self.limit_spin.setRange(1, 999)
        self.limit_spin.setValue(20)
        self.limit_spin.setEnabled(False)
        limit_row.addWidget(self.limit_check)
        limit_row.addWidget(self.limit_spin)
        limit_row.addWidget(
            QLabel(t("limit_hint")))
        limit_row.addStretch()
        self.limit_check.toggled.connect(self.limit_spin.setEnabled)
        q_layout.addLayout(limit_row)
        layout.addWidget(q_group)

        # ── Timer ───────────────────────────────────────────────────────────
        timer_group = QGroupBox(t("timer"))
        timer_layout = QHBoxLayout(timer_group)
        self.timer_check = QCheckBox(t("enable_timer"))
        self.timer_spin  = QSpinBox()
        self.timer_spin.setRange(1, 300)
        self.timer_spin.setValue(60)
        self.timer_spin.setEnabled(False)
        self.timer_check.toggled.connect(self.timer_spin.setEnabled)
        timer_layout.addWidget(self.timer_check)
        timer_layout.addWidget(self.timer_spin)
        timer_layout.addWidget(QLabel(t("minutes")))
        timer_layout.addStretch()
        layout.addWidget(timer_group)

        # ── Scoring ─────────────────────────────────────────────────────────
        score_group = QGroupBox(t("scoring_system"))
        score_layout = QFormLayout(score_group)
        score_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.scoring_combo = QComboBox()
        self.scoring_combo.addItems([
            t("mode_raw"),
            t("mode_partial"),
            t("mode_negative"),
        ])
        score_layout.addRow(t("method"), self.scoring_combo)
        layout.addWidget(score_group)

        # ── Shuffle ─────────────────────────────────────────────────────────
        self.shuffle_check = QCheckBox(t("shuffle"))
        self.shuffle_check.setChecked(True)
        layout.addWidget(self.shuffle_check)

        # ── Buttons ─────────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(t("cancel"))
        cancel_btn.clicked.connect(self.reject)
        self.start_btn = QPushButton(t("start_exam"))
        self.start_btn.setDefault(True)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.start_btn)
        layout.addLayout(btn_layout)

    # ─────────────────────────────────────────────────────────────────────────

    def _open_picker(self):
        nt = self.note_type_combo.currentText().strip() or DEFAULT_NOTE_TYPE
        dlg = CardPickerDialog(self, nt)
        if dlg.exec():
            self._picked_ids  = dlg.selected_note_ids()
            self._picked_meta = dlg.note_meta()
            n = len(self._picked_ids)
            self.pick_label.setText(
                t("n_picked_one" if n == 1 else "n_picked_many", n=n))
            self.pick_label.setStyleSheet(
                "color:#16a34a;font-weight:bold;")
            self.limit_spin.setMaximum(n)
            self.start_btn.setEnabled(True)

    def _start(self):
        self.start_btn.setEnabled(False)
        self.start_btn.setText(t("loading"))

        note_type = self.note_type_combo.currentText().strip() or DEFAULT_NOTE_TYPE
        note_ids  = list(self._picked_ids)

        # ── Smart sampling across sub-decks ──────────────────────────────
        if self.limit_check.isChecked():
            limit = self.limit_spin.value()
            pairs = [
                (nid, self._picked_meta.get(nid, {"deck": ""}))
                for nid in note_ids
            ]
            note_ids = _smart_sample(pairs, limit)

        # Shuffle only changes final exam order, never membership logic.
        if self.shuffle_check.isChecked():
            random.shuffle(note_ids)

        questions = []
        for nid in note_ids:
            note = mw.col.get_note(nid)
            q = _parse_note(note, note_type)
            if q:
                q["nid"] = nid
                questions.append(q)

        if not questions:
            QMessageBox.warning(
                self, t("no_valid_title"), t("no_valid_msg"))
            self.start_btn.setEnabled(True)
            self.start_btn.setText(t("start_exam"))
            return

        scoring_modes = ["raw", "partial", "negative"]
        scoring = {
            "mode": scoring_modes[self.scoring_combo.currentIndex()],
        }
        timer_seconds = (self.timer_spin.value() * 60
                         if self.timer_check.isChecked() else 0)
        raw_exam_name = self.exam_name_edit.text().strip()
        exam_name = (raw_exam_name.replace(" ", "_") or "Unnamed_Exam")
        save_history = bool(raw_exam_name)

        if not save_history:
            answer = QMessageBox.question(
                self,
                t("no_name_title"),
                t("no_name_msg"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.start_btn.setEnabled(True)
                self.start_btn.setText(t("start_exam"))
                return

        self.accept()

        from .exam_window import ExamWindow
        win = ExamWindow(mw, questions, timer_seconds, scoring, exam_name, save_history=save_history)
        win.showMaximized()
