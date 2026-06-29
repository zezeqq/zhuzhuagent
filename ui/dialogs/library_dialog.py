from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout,
)

from core.file_manager import import_file, list_library_files
from core.agent_context import current_project
from db.database import execute
from rag.indexer import index_file, reindex_all_files
from rag.embedding_provider import embedding_status


class LibraryDialog(QDialog):
    """资料库：导入文件、向量索引与列表管理。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("资料库")
        self.setMinimumSize(560, 420)
        self.setObjectName("SettingsDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        hint = QLabel("导入 PDF、Word、Markdown 等文档后自动分块并建立语义向量索引（bge-small-zh / API / 关键词兜底）。Agent 对话时会检索当前项目与全局资料库。")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._backend_label = QLabel()
        self._backend_label.setObjectName("MutedLabel")
        self._backend_label.setWordWrap(True)
        layout.addWidget(self._backend_label)
        self._refresh_backend_label()

        toolbar = QHBoxLayout()
        import_btn = QPushButton("导入文件…")
        import_btn.setProperty("variant", "primary")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self._import_files)
        toolbar.addWidget(import_btn)

        reindex_btn = QPushButton("重建全部索引")
        reindex_btn.setProperty("variant", "secondary")
        reindex_btn.setCursor(Qt.PointingHandCursor)
        reindex_btn.clicked.connect(self._reindex_all)
        toolbar.addWidget(reindex_btn)

        del_btn = QPushButton("删除选中")
        del_btn.setProperty("variant", "ghost")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(del_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self._list, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("关闭")
        close.setProperty("variant", "secondary")
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        layout.addLayout(close_row)

        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for row in list_library_files(
            current_project()["id"] if current_project() else None
        ):
            fid = row["id"]
            name = row.get("file_name", "")
            ftype = row.get("file_type", "")
            size = row.get("file_size", 0) or 0
            size_kb = f"{size // 1024} KB" if size else ""
            item = QListWidgetItem(f"{name}  ({ftype}, {size_kb})")
            item.setData(Qt.UserRole, fid)
            item.setToolTip(row.get("file_path", ""))
            self._list.addItem(item)

    def _refresh_backend_label(self) -> None:
        st = embedding_status()
        backend = st.get("backend", "sparse")
        labels = {
            "local": f"当前向量引擎：本地语义模型（{st.get('local_model', '')}）",
            "ollama": f"当前向量引擎：Ollama（{st.get('ollama_model', '')}）",
            "api": f"当前向量引擎：Embedding API（{st.get('api_model', '')}）",
            "sparse": (
                "当前向量引擎：词袋兜底。"
                " 启用语义检索：pip install fastembed，或运行 Ollama 并 ollama pull nomic-embed-text，"
                "或在设置中配置 rag_embedding_api_base/key 后重建索引。"
            ),
        }
        self._backend_label.setText(labels.get(backend, labels["sparse"]))

    def _import_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要导入的文件",
            "",
            "文档 (*.pdf *.docx *.doc *.txt *.md *.csv *.json);;所有文件 (*.*)",
        )
        if not paths:
            return
        errors: list[str] = []
        project = current_project()
        project_id = project["id"] if project else None
        for path in paths:
            try:
                fid = import_file(path, project_id=project_id)
                index_file(fid)
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
        self._refresh_list()
        self._refresh_backend_label()
        if errors:
            QMessageBox.warning(self, "部分导入失败", "\n".join(errors[:8]))
        elif paths:
            QMessageBox.information(self, "导入完成", f"已成功导入并索引 {len(paths)} 个文件。")

    def _reindex_all(self) -> None:
        try:
            count = reindex_all_files()
            self._refresh_backend_label()
            st = embedding_status()
            backend = st.get("backend", "sparse")
            QMessageBox.information(
                self,
                "重建完成",
                f"已重建 {count} 个文件的向量索引。\n当前引擎：{backend}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "重建失败", str(exc))

    def _delete_selected(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除选中的 {len(items)} 条记录？\n（不会删除磁盘上的原始文件）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for item in items:
            fid = item.data(Qt.UserRole)
            execute("DELETE FROM file_chunks WHERE file_id=?", (fid,))
            execute("DELETE FROM files WHERE id=?", (fid,))
        self._refresh_list()
