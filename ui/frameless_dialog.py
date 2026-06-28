"""无边框对话框：自定义顶栏，与主窗口风格一致。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.i18n import t
from ui.window_chrome import TitleBarFrame, apply_window_effects


def setup_frameless_dialog(
    dialog: QDialog,
    *,
    title_key: str = "settings.title",
    min_size: tuple[int, int] = (960, 640),
) -> tuple[QLabel, QWidget]:
    """Configure a QDialog as frameless with custom title bar. Returns (title_label, body_widget)."""
    dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    dialog.setMinimumSize(*min_size)
    dialog.setAttribute(Qt.WA_TranslucentBackground, False)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    title_bar = TitleBarFrame(dialog)
    title_bar.setObjectName("DialogTitleBar")
    title_bar.setFixedHeight(32)
    tb_layout = QHBoxLayout(title_bar)
    tb_layout.setContentsMargins(12, 0, 4, 0)
    tb_layout.setSpacing(8)

    title_label = QLabel(t(title_key))
    title_label.setObjectName("DialogTitleLabel")
    tb_layout.addWidget(title_label)
    tb_layout.addStretch()

    close_btn = QPushButton("✕")
    close_btn.setObjectName("TitleBarCloseButton")
    close_btn.setCursor(Qt.PointingHandCursor)
    close_btn.setFixedSize(36, 28)
    close_btn.clicked.connect(dialog.close)
    tb_layout.addWidget(close_btn)

    outer.addWidget(title_bar)

    body = QWidget()
    body.setObjectName("DialogBody")
    outer.addWidget(body, 1)

    dialog._frameless_title_label = title_label  # type: ignore[attr-defined]
    dialog._frameless_title_key = title_key  # type: ignore[attr-defined]

    return title_label, body


def on_frameless_dialog_show(dialog: QDialog) -> None:
    apply_window_effects(dialog)
