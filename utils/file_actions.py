"""文件右键菜单：打开、定位、复制、删除等。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget


def open_file_path(file_path: str | Path, parent: QWidget | None = None) -> bool:
    path = Path(file_path)
    if not path.exists():
        QMessageBox.warning(parent, "无法打开", f"文件不存在：\n{path}")
        return False
    try:
        os.startfile(str(path))
        return True
    except OSError as exc:
        QMessageBox.warning(parent, "无法打开", f"无法用系统默认程序打开：\n{path}\n\n{exc}")
        return False


def reveal_in_explorer(file_path: str | Path, parent: QWidget | None = None) -> bool:
    """在资源管理器中显示文件或文件夹。"""
    path = Path(file_path).resolve()
    if not path.exists():
        QMessageBox.warning(parent, "无法打开位置", f"路径不存在：\n{path}")
        return False
    try:
        if sys.platform == "win32":
            if path.is_file():
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            folder = path if path.is_dir() else path.parent
            subprocess.Popen(["xdg-open", str(folder)])
        return True
    except OSError as exc:
        QMessageBox.warning(parent, "无法打开位置", f"无法打开文件所在位置：\n{path}\n\n{exc}")
        return False


def copy_text(text: str, parent: QWidget | None = None) -> None:
    QGuiApplication.clipboard().setText(text)


def delete_file_path(
    file_path: str | Path,
    parent: QWidget | None = None,
    *,
    on_deleted: Callable[[], None] | None = None,
) -> bool:
    path = Path(file_path)
    if not path.exists():
        QMessageBox.warning(parent, "无法删除", f"文件不存在：\n{path}")
        return False
    if path.is_dir():
        QMessageBox.warning(parent, "无法删除", "请选择文件，文件夹请手动删除。")
        return False
    reply = QMessageBox.question(
        parent,
        "确认删除",
        f"确定删除此文件吗？\n{path.name}\n\n此操作不可恢复。",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return False
    try:
        path.unlink()
        if on_deleted:
            on_deleted()
        return True
    except OSError as exc:
        QMessageBox.warning(parent, "删除失败", str(exc))
        return False


def exec_file_context_menu(
    parent: QWidget,
    file_path: str,
    global_pos,
    *,
    on_preview: Callable[[], None] | None = None,
    on_after_delete: Callable[[], None] | None = None,
) -> None:
    """弹出文件右键菜单。"""
    path = Path(file_path)
    menu = QMenu(parent)

    if path.is_file():
        menu.addAction("📂 打开", lambda: open_file_path(path, parent))
    elif path.is_dir():
        menu.addAction("📂 打开文件夹", lambda: reveal_in_explorer(path, parent))
    else:
        menu.addAction("📂 打开所在位置", lambda: reveal_in_explorer(path.parent, parent))

    menu.addAction("📁 在文件资源管理器中显示", lambda: reveal_in_explorer(path, parent))

    if on_preview and path.is_file():
        menu.addAction("👁 在预览面板中查看", on_preview)

    menu.addSeparator()
    menu.addAction("📋 复制完整路径", lambda: copy_text(str(path.resolve()), parent))
    menu.addAction("📋 复制文件名", lambda: copy_text(path.name, parent))

    if path.is_file():
        menu.addSeparator()
        menu.addAction("🗑 删除文件", lambda: delete_file_path(
            path, parent, on_deleted=on_after_delete
        ))

    menu.exec(global_pos)
