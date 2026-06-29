"""发送按钮：悬停弹出「引导 / 正常发送」菜单。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QMenu, QPushButton, QWidget

from ui.i18n import t


class SendMenuButton(QPushButton):
    send_normal = Signal()
    send_guide = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("↑", parent)
        self.setObjectName("SendButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(48, 48)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(220)
        self._hover_timer.timeout.connect(self._show_menu)
        self._menu_open = False
        self.clicked.connect(self._on_clicked)

    def set_busy(self, busy: bool) -> None:
        self.setProperty("busy", "true" if busy else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        tip = t("send_busy_tip") if busy else t("send_enter")
        self.setToolTip(tip)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if not self._menu_open:
            self._hover_timer.start()

    def leaveEvent(self, event) -> None:
        self._hover_timer.stop()
        super().leaveEvent(event)

    def _on_clicked(self) -> None:
        if self.property("busy") == "true":
            self.send_guide.emit()
        else:
            self.send_normal.emit()

    def _show_menu(self) -> None:
        if not self.underMouse() or self._menu_open:
            return
        self._menu_open = True
        menu = QMenu(self)
        menu.setObjectName("SendHoverMenu")
        busy = self.property("busy") == "true"

        act_guide = menu.addAction(t("send_menu_guide"))
        act_guide.setEnabled(busy)
        if not busy:
            act_guide.setToolTip(t("send_menu_guide_disabled_tip"))

        act_normal = menu.addAction(t("send_menu_normal"))
        act_guide.triggered.connect(self.send_guide.emit)
        act_normal.triggered.connect(self.send_normal.emit)
        menu.aboutToHide.connect(self._on_menu_closed)

        global_pos = self.mapToGlobal(QPoint(0, 0))
        menu.popup(global_pos + QPoint(0, -menu.sizeHint().height() - 6))

    def _on_menu_closed(self) -> None:
        self._menu_open = False
