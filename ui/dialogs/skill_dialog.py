from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget, QVBoxLayout,
    QWidget,
)

from agent_runtime.skill_files import list_skill_files, read_skill_file, write_skill_file
from agent_runtime.skill_installer import install_market_skill, install_skill_from_url
from agent_runtime.tool_executor import load_installed_handlers
from core.skill_catalog import (
    INSTALLED_SKILLS_DIR,
    RECOMMENDED_SKILLS,
    SKILL_CATEGORIES,
    get_installed_package_names,
    is_skill_installed,
)
from db.database import execute, query_all


SKILL_ROOT = INSTALLED_SKILLS_DIR


class SkillDialog(QDialog):
    def __init__(self, parent=None, *, initial_tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("技能商店")
        self.setMinimumSize(960, 620)
        self.setObjectName("SettingsDialog")
        self._packages: list[dict] = []
        self._editor_dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("SkillHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 16, 24, 16)
        title = QLabel("技能商店")
        title.setObjectName("SettingsSection")
        h_layout.addWidget(title)
        path_hint = QLabel(f"Skill 文件目录: {INSTALLED_SKILLS_DIR}")
        path_hint.setObjectName("MutedLabel")
        path_hint.setToolTip("每个 Skill 是一个子文件夹，核心是 SKILL.md")
        h_layout.addWidget(path_hint)
        open_dir_btn = QPushButton("📂 打开目录")
        open_dir_btn.setProperty("variant", "ghost")
        open_dir_btn.setCursor(Qt.PointingHandCursor)
        open_dir_btn.clicked.connect(self._open_skill_root)
        h_layout.addWidget(open_dir_btn)
        h_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setProperty("variant", "ghost")
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.close)
        h_layout.addWidget(close_btn)
        layout.addWidget(header)

        tabs = QTabWidget()
        tabs.setObjectName("SkillTabs")
        tabs.addTab(self._market_tab(), "推荐技能")
        tabs.addTab(self._installed_tab(), "我的 Skill")
        tabs.addTab(self._custom_tab(), "从 URL 安装")
        if 0 <= initial_tab < tabs.count():
            tabs.setCurrentIndex(initial_tab)
        layout.addWidget(tabs, 1)

    def _market_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        download_box = QFrame()
        download_box.setObjectName("SkillDownloadBar")
        dl_layout = QVBoxLayout(download_box)
        dl_layout.setContentsMargins(14, 12, 14, 12)
        dl_layout.setSpacing(8)
        dl_title = QLabel("从 URL / GitHub 下载安装")
        dl_title.setObjectName("CardTitle")
        dl_layout.addWidget(dl_title)
        dl_hint = QLabel(
            "粘贴 Skill 仓库或 ZIP 地址安装。"
            "安装后请到「我的 Skill」标签查看 / 编辑 SKILL.md。"
        )
        dl_hint.setObjectName("MutedLabel")
        dl_hint.setWordWrap(True)
        dl_layout.addWidget(dl_hint)
        dl_row = QHBoxLayout()
        self._market_url_input = QLineEdit()
        self._market_url_input.setPlaceholderText(
            "https://github.com/user/skill-repo  或  https://example.com/skill.zip"
        )
        self._market_url_input.setMinimumHeight(36)
        self._market_url_input.returnPressed.connect(self._install_from_url_market)
        dl_row.addWidget(self._market_url_input, 1)
        dl_btn = QPushButton("下载安装")
        dl_btn.setProperty("variant", "primary")
        dl_btn.setCursor(Qt.PointingHandCursor)
        dl_btn.clicked.connect(self._install_from_url_market)
        dl_row.addWidget(dl_btn)
        dl_layout.addLayout(dl_row)
        self._market_install_status = QLabel("")
        self._market_install_status.setObjectName("MutedLabel")
        self._market_install_status.setWordWrap(True)
        dl_layout.addWidget(self._market_install_status)
        layout.addWidget(download_box)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._category_btns = {}
        for cat in SKILL_CATEGORIES:
            btn = QPushButton(cat)
            btn.setObjectName("FilterButton")
            btn.setCheckable(True)
            btn.setChecked(cat == "全部")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=cat: self._filter_skills(c))
            self._category_btns[cat] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("ArtifactScroll")
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        self._skill_cards = []
        self._render_skills("全部")
        return page

    def _render_skills(self, category: str) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._skill_cards.clear()
        installed = get_installed_package_names()
        skills = RECOMMENDED_SKILLS if category == "全部" else [
            s for s in RECOMMENDED_SKILLS if s["category"] == category
        ]
        for idx, skill in enumerate(skills):
            card = self._skill_card(skill, installed)
            self._grid_layout.addWidget(card, idx // 3, idx % 3)
            self._skill_cards.append(card)
        for col in range(3):
            self._grid_layout.setColumnStretch(col, 1)

    def _skill_card(self, skill: dict, installed: set[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("ActionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        top = QHBoxLayout()
        icon = skill.get("icon", "⚡")
        name_label = QLabel(f"{icon}  {skill['display']}")
        name_label.setObjectName("CardTitle")
        top.addWidget(name_label, 1)
        cat_label = QLabel(skill["category"])
        cat_label.setObjectName("MutedLabel")
        top.addWidget(cat_label)
        layout.addLayout(top)
        desc_label = QLabel(skill["desc"])
        desc_label.setObjectName("MutedLabel")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        already = is_skill_installed(skill, installed)
        install_btn = QPushButton("✓ 已安装" if already else "＋ 安装")
        install_btn.setProperty("variant", "secondary")
        install_btn.setCursor(Qt.PointingHandCursor)
        install_btn.setFixedHeight(30)
        install_btn.setEnabled(not already)
        install_btn.clicked.connect(lambda: self._install_market(skill, install_btn))
        layout.addWidget(install_btn)
        return card

    def _install_market(self, skill: dict, btn: QPushButton) -> None:
        btn.setEnabled(False)
        btn.setText("安装中…")
        try:
            download_url = skill.get("download_url") or skill.get("url")
            if download_url:
                result = install_skill_from_url(download_url)
            else:
                result = install_market_skill(
                    skill["name"],
                    skill["display"],
                    skill["desc"],
                    skill_md=skill.get("skill_md", ""),
                )
            load_installed_handlers()
            btn.setText("✓ 已安装")
            path = result.get("install_path", "")
            QMessageBox.information(
                self, "安装成功",
                f"技能「{skill['display']}」已安装。\n\n路径：{path}\n\n新开对话或继续聊天时 Agent 会自动加载。",
            )
            self._refresh_installed()
            self._render_skills(self._current_category())
        except Exception as exc:
            btn.setEnabled(True)
            btn.setText("＋ 安装")
            QMessageBox.warning(self, "安装失败", str(exc))

    def _current_category(self) -> str:
        for cat, btn in self._category_btns.items():
            if btn.isChecked():
                return cat
        return "全部"

    def _install_from_url_market(self) -> None:
        url = self._market_url_input.text().strip()
        if not url:
            self._market_install_status.setText("请输入下载地址")
            return
        self._market_install_status.setText("正在下载安装…")
        try:
            result = install_skill_from_url(url)
            load_installed_handlers()
            path = result.get("install_path", "")
            name = result.get("package_name", "")
            self._market_install_status.setText(f"✓ 已安装 {name} → {path}")
            self._market_url_input.clear()
            self._refresh_installed()
            self._render_skills(self._current_category())
        except Exception as exc:
            self._market_install_status.setText(f"安装失败：{exc}")

    def _after_url_install(self, result: dict) -> None:
        load_installed_handlers()
        self._refresh_installed()
        if hasattr(self, "_market_install_status"):
            self._market_install_status.setText(
                f"✓ 已安装 {result.get('package_name', '')} → {result.get('install_path', '')}"
            )
        self._render_skills(self._current_category())

    def _filter_skills(self, category: str) -> None:
        for cat, btn in self._category_btns.items():
            btn.setChecked(cat == category)
        self._render_skills(category)

    def _installed_tab(self) -> QWidget:
        page = QWidget()
        self._installed_page = page
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hint = QLabel(
            "左侧选择 Skill，右侧查看 / 编辑 SKILL.md 等文件。"
            "保存后下一条 Agent 对话即生效（需保持「已启用」）。"
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        upload_btn = QPushButton("📦 上传技能包")
        upload_btn.setProperty("variant", "secondary")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._upload_skill_package)
        toolbar.addWidget(upload_btn)

        create_btn = QPushButton("＋ 创建技能")
        create_btn.setProperty("variant", "primary")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.clicked.connect(self._create_skill)
        toolbar.addWidget(create_btn)

        toolbar.addStretch()

        self._batch_select_all = QCheckBox("批量选择")
        self._batch_select_all.clicked.connect(self._toggle_select_all)
        toolbar.addWidget(self._batch_select_all)

        self._batch_uninstall_btn = QPushButton("批量卸载")
        self._batch_uninstall_btn.setProperty("variant", "danger")
        self._batch_uninstall_btn.setCursor(Qt.PointingHandCursor)
        self._batch_uninstall_btn.setVisible(False)
        self._batch_uninstall_btn.clicked.connect(self._batch_uninstall)
        toolbar.addWidget(self._batch_uninstall_btn)

        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("SkillEditorSplitter")

        left = QFrame()
        left.setObjectName("SkillListPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        left_title = QLabel("已安装的 Skill")
        left_title.setObjectName("CardTitle")
        left_layout.addWidget(left_title)
        self._skill_list = QListWidget()
        self._skill_list.setObjectName("SkillList")
        self._skill_list.currentRowChanged.connect(self._on_skill_list_selected)
        left_layout.addWidget(self._skill_list, 1)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("SkillEditorPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 8, 8, 8)
        right_layout.setSpacing(8)

        self._editor_title = QLabel("选择左侧 Skill 以查看文件")
        self._editor_title.setObjectName("CardTitle")
        right_layout.addWidget(self._editor_title)

        self._editor_path = QLabel("")
        self._editor_path.setObjectName("MutedLabel")
        self._editor_path.setWordWrap(True)
        self._editor_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right_layout.addWidget(self._editor_path)

        meta_row = QHBoxLayout()
        self._pkg_enable_btn = QPushButton("已启用")
        self._pkg_enable_btn.setProperty("variant", "secondary")
        self._pkg_enable_btn.setCheckable(True)
        self._pkg_enable_btn.setEnabled(False)
        self._pkg_enable_btn.clicked.connect(self._toggle_selected_skill)
        meta_row.addWidget(self._pkg_enable_btn)
        meta_row.addStretch()
        open_pkg_btn = QPushButton("📂 打开文件夹")
        open_pkg_btn.setProperty("variant", "ghost")
        open_pkg_btn.setCursor(Qt.PointingHandCursor)
        open_pkg_btn.clicked.connect(self._open_selected_folder)
        meta_row.addWidget(open_pkg_btn)
        right_layout.addLayout(meta_row)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("文件:"))
        self._file_combo = QComboBox()
        self._file_combo.setMinimumWidth(180)
        self._file_combo.currentIndexChanged.connect(self._on_file_combo_changed)
        file_row.addWidget(self._file_combo, 1)
        self._save_file_btn = QPushButton("💾 保存")
        self._save_file_btn.setProperty("variant", "primary")
        self._save_file_btn.setEnabled(False)
        self._save_file_btn.clicked.connect(self._save_current_file)
        file_row.addWidget(self._save_file_btn)
        right_layout.addLayout(file_row)

        self._file_editor = QPlainTextEdit()
        self._file_editor.setObjectName("SkillFileEditor")
        self._file_editor.setPlaceholderText("SKILL.md 内容将显示在这里…")
        font = QFont("Cascadia Mono", 10)
        if not font.exactMatch():
            font = QFont("Consolas", 10)
        self._file_editor.setFont(font)
        self._file_editor.setReadOnly(True)
        self._file_editor.textChanged.connect(self._on_editor_changed)
        right_layout.addWidget(self._file_editor, 1)

        self._editor_status = QLabel("")
        self._editor_status.setObjectName("MutedLabel")
        right_layout.addWidget(self._editor_status)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 640])

        layout.addWidget(splitter, 1)

        self._installed_checkboxes: list[tuple[QCheckBox, dict]] = []
        self._current_pkg: dict | None = None
        self._current_file_path: Path | None = None
        self._loading_editor = False
        self._refresh_installed()
        return page

    def _refresh_installed(self) -> None:
        prev_id = self._current_pkg.get("id") if self._current_pkg else None
        self._skill_list.clear()
        self._installed_checkboxes.clear()
        self._packages = query_all("SELECT * FROM installed_skill_packages ORDER BY id DESC")

        if not self._packages:
            self._current_pkg = None
            self._clear_editor("还没有安装 Skill。去「推荐技能」安装，或点「创建技能」。")
            return

        select_row = 0
        for i, pkg in enumerate(self._packages):
            display = pkg.get("display_name") or pkg["package_name"]
            enabled = "✓" if pkg.get("enabled") else "○"
            item = QListWidgetItem(f"{enabled}  {display}")
            item.setData(Qt.UserRole, dict(pkg))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self._skill_list.addItem(item)
            if prev_id is not None and pkg.get("id") == prev_id:
                select_row = i

        self._skill_list.setCurrentRow(select_row)

    def _clear_editor(self, message: str = "") -> None:
        self._loading_editor = True
        self._file_combo.blockSignals(True)
        self._file_combo.clear()
        self._file_combo.blockSignals(False)
        self._file_editor.clear()
        self._file_editor.setReadOnly(True)
        self._loading_editor = False
        self._editor_dirty = False
        self._current_file_path = None
        self._save_file_btn.setEnabled(False)
        self._pkg_enable_btn.setEnabled(False)
        self._editor_title.setText("选择左侧 Skill 以查看文件")
        self._editor_path.setText(message)
        self._editor_status.setText("")

    def _on_skill_list_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._packages):
            self._current_pkg = None
            self._clear_editor()
            return
        item = self._skill_list.item(row)
        if not item:
            return
        pkg = item.data(Qt.UserRole) or self._packages[row]
        self._current_pkg = dict(pkg)
        self._load_pkg_into_editor(self._current_pkg)

    def _load_pkg_into_editor(self, pkg: dict) -> None:
        install_path = Path(pkg.get("install_path") or "")
        display = pkg.get("display_name") or pkg.get("package_name") or "Skill"
        self._editor_title.setText(display)
        self._editor_path.setText(str(install_path) if install_path.is_dir() else "路径不存在")

        enabled = bool(pkg.get("enabled"))
        self._pkg_enable_btn.setEnabled(True)
        self._pkg_enable_btn.blockSignals(True)
        self._pkg_enable_btn.setChecked(enabled)
        self._pkg_enable_btn.setText("已启用" if enabled else "已禁用")
        self._pkg_enable_btn.setProperty("variant", "secondary" if enabled else "ghost")
        self._pkg_enable_btn.style().unpolish(self._pkg_enable_btn)
        self._pkg_enable_btn.style().polish(self._pkg_enable_btn)
        self._pkg_enable_btn.blockSignals(False)

        files = list_skill_files(install_path) if install_path.is_dir() else []
        self._file_combo.blockSignals(True)
        self._file_combo.clear()
        for label, path in files:
            self._file_combo.addItem(label, str(path))
        self._file_combo.blockSignals(False)

        if not files:
            self._clear_editor(f"{install_path}\n（未找到 SKILL.md / skill.json，可点「打开文件夹」查看）")
            self._editor_title.setText(display)
            return

        skill_md_idx = next((i for i, (lbl, _) in enumerate(files) if lbl == "SKILL.md"), 0)
        self._file_combo.setCurrentIndex(skill_md_idx)
        self._load_file_at_index(skill_md_idx)

    def _load_file_at_index(self, index: int) -> None:
        if index < 0:
            return
        path_str = self._file_combo.itemData(index)
        if not path_str:
            return
        path = Path(path_str)
        if not path.is_file():
            self._editor_status.setText(f"文件不存在: {path}")
            return
        self._loading_editor = True
        try:
            content = read_skill_file(path)
        except Exception as exc:
            content = f"读取失败: {exc}"
        self._current_file_path = path
        self._file_editor.setPlainText(content)
        editable = path.suffix.lower() in {".md", ".json", ".py", ".txt"}
        self._file_editor.setReadOnly(not editable)
        self._save_file_btn.setEnabled(editable)
        self._editor_dirty = False
        self._loading_editor = False
        self._editor_status.setText(
            f"正在查看: {path.name}  ({len(content)} 字符)"
            + (" — 可编辑，记得保存" if editable else " — 只读")
        )

    def _on_file_combo_changed(self, index: int) -> None:
        if self._editor_dirty:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "当前文件有未保存修改，是否放弃？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._load_file_at_index(index)

    def _on_editor_changed(self) -> None:
        if self._loading_editor or not self._current_file_path:
            return
        self._editor_dirty = True
        self._editor_status.setText("● 有未保存的更改")

    def _save_current_file(self) -> None:
        if not self._current_file_path:
            return
        try:
            write_skill_file(self._current_file_path, self._file_editor.toPlainText())
            self._editor_dirty = False
            self._editor_status.setText(f"✓ 已保存: {self._current_file_path.name}（下一条对话生效）")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def _toggle_selected_skill(self, checked: bool) -> None:
        if not self._current_pkg:
            return
        execute(
            "UPDATE installed_skill_packages SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (1 if checked else 0, self._current_pkg["id"]),
        )
        self._current_pkg["enabled"] = 1 if checked else 0
        self._pkg_enable_btn.setText("已启用" if checked else "已禁用")
        self._pkg_enable_btn.setProperty("variant", "secondary" if checked else "ghost")
        self._pkg_enable_btn.style().unpolish(self._pkg_enable_btn)
        self._pkg_enable_btn.style().polish(self._pkg_enable_btn)
        row = self._skill_list.currentRow()
        if row >= 0:
            item = self._skill_list.item(row)
            display = self._current_pkg.get("display_name") or self._current_pkg["package_name"]
            item.setText(f"{'✓' if checked else '○'}  {display}")
        self._editor_status.setText("启用状态已更新")

    def _open_skill_root(self) -> None:
        import os
        SKILL_ROOT.mkdir(parents=True, exist_ok=True)
        os.startfile(str(SKILL_ROOT))

    def _open_selected_folder(self) -> None:
        if not self._current_pkg:
            return
        import os
        path = Path(self._current_pkg.get("install_path") or "")
        if path.is_dir():
            os.startfile(str(path))
        else:
            QMessageBox.warning(self, "提示", f"文件夹不存在:\n{path}")

    def _toggle_select_all(self, checked: bool) -> None:
        for i in range(self._skill_list.count()):
            item = self._skill_list.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._update_batch_visibility()

    def _update_batch_visibility(self) -> None:
        any_checked = any(
            self._skill_list.item(i).checkState() == Qt.Checked
            for i in range(self._skill_list.count())
        )
        self._batch_uninstall_btn.setVisible(any_checked)

    def _batch_uninstall(self) -> None:
        selected: list[dict] = []
        for i in range(self._skill_list.count()):
            item = self._skill_list.item(i)
            if item.checkState() == Qt.Checked:
                pkg = item.data(Qt.UserRole)
                if pkg:
                    selected.append(dict(pkg))
        if not selected:
            return
        confirm = QMessageBox.question(
            self, "确认卸载",
            f"确定要卸载选中的 {len(selected)} 个 Skill 吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        for pkg in selected:
            execute("DELETE FROM installed_skill_packages WHERE id=?", (pkg["id"],))
            install_path = pkg.get("install_path", "")
            if install_path:
                p = Path(install_path)
                if p.exists() and p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
        self._current_pkg = None
        self._refresh_installed()
        self._render_skills(self._current_category())

    def _upload_skill_package(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择技能包文件夹")
        if not path:
            zip_path, _ = QFileDialog.getOpenFileName(self, "选择技能包 ZIP", "", "ZIP 文件 (*.zip)")
            if not zip_path:
                return
            path = zip_path

        try:
            src = Path(path)
            if src.is_dir():
                pkg_name = src.name.lower().replace(" ", "_")
                dest = SKILL_ROOT / pkg_name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                manifest = self._find_or_create_manifest(dest, pkg_name)
                self._register_uploaded(pkg_name, manifest, dest)
            else:
                result = install_skill_from_url(str(src))
            load_installed_handlers()
            self._refresh_installed()
            if hasattr(self, "_category_btns"):
                self._render_skills(self._current_category())
            QMessageBox.information(self, "上传成功", "技能包已成功安装。")
        except Exception as exc:
            QMessageBox.warning(self, "上传失败", str(exc))

    def _find_or_create_manifest(self, root: Path, pkg_name: str) -> dict:
        for name in ["skill.json", "dna_skill.json", "manifest.json"]:
            p = root / name
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        manifest = {
            "name": pkg_name,
            "display_name": pkg_name,
            "version": "0.1.0",
            "description": "本地上传的技能包",
            "entry": "skill.py",
        }
        (root / "skill.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def _register_uploaded(self, pkg_name: str, manifest: dict, install_path: Path) -> None:
        from db.database import insert, query_one
        existing = query_one("SELECT id FROM installed_skill_packages WHERE package_name=?", (pkg_name,))
        data = {
            "package_name": pkg_name,
            "display_name": manifest.get("display_name") or pkg_name,
            "version": str(manifest.get("version") or "0.1.0"),
            "source_type": "upload",
            "source_url": "",
            "install_path": str(install_path),
            "manifest_json": json.dumps(manifest, ensure_ascii=False),
            "enabled": 1,
        }
        if existing:
            execute(
                "UPDATE installed_skill_packages SET display_name=?, version=?, source_type=?, install_path=?, manifest_json=?, enabled=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (data["display_name"], data["version"], data["source_type"], data["install_path"], data["manifest_json"], existing["id"]),
            )
        else:
            insert("installed_skill_packages", data)

    def _create_skill(self) -> None:
        name, ok = QInputDialog.getText(self, "创建技能", "请输入技能名称：")
        if not ok or not name.strip():
            return
        pkg_name = name.strip().lower().replace(" ", "_")
        skill_dir = SKILL_ROOT / pkg_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"# {name.strip()}\n\n"
            f"## 描述\n\n在此描述该技能的用途和使用场景。\n\n"
            f"## 触发条件\n\n当用户请求...时触发此技能。\n\n"
            f"## 执行步骤\n\n1. 步骤一\n2. 步骤二\n3. 步骤三\n\n"
            f"## 输出格式\n\n描述预期的输出格式。\n",
            encoding="utf-8",
        )

        manifest = {
            "name": pkg_name,
            "display_name": name.strip(),
            "version": "0.1.0",
            "description": f"自定义技能: {name.strip()}",
            "entry": "SKILL.md",
            "prompt_entry": "SKILL.md",
        }
        (skill_dir / "skill.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        self._register_uploaded(pkg_name, manifest, skill_dir)
        self._refresh_installed()
        self._skill_list.setCurrentRow(0)
        QMessageBox.information(
            self, "创建成功",
            f"技能「{name.strip()}」已创建。\n\n请在右侧编辑 SKILL.md，保存后 Agent 下一条对话生效。",
        )

    def _custom_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        desc = QLabel("输入 GitHub 仓库地址、ZIP 文件或 Python 文件 URL，自动下载并安装到本地。")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://github.com/user/skill-repo 或 https://example.com/skill.zip")
        self._url_input.setMinimumHeight(38)
        row.addWidget(self._url_input, 1)
        install_btn = QPushButton("安装")
        install_btn.setProperty("variant", "primary")
        install_btn.setCursor(Qt.PointingHandCursor)
        install_btn.clicked.connect(self._install_from_url)
        row.addWidget(install_btn)
        layout.addLayout(row)
        self._install_status = QLabel("")
        self._install_status.setWordWrap(True)
        layout.addWidget(self._install_status)
        layout.addStretch()
        return page

    def _install_from_url(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            self._install_status.setText("请输入 URL")
            return
        self._install_status.setText("正在下载安装…")
        try:
            result = install_skill_from_url(url)
            self._install_status.setText(
                f"安装成功：{result['package_name']}  ➜  {result['install_path']}"
            )
            self._url_input.clear()
            self._after_url_install(result)
        except Exception as exc:
            self._install_status.setText(f"安装失败：{exc}")
