"""Open settings dialog with live-apply wired to the main window."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ui.dialogs.settings_dialog import SettingsDialog

_open_dialogs: list[SettingsDialog] = []


def open_settings_dialog(parent, page: int = 0) -> None:
    window = parent.window() if hasattr(parent, "window") else parent

    for existing in list(_open_dialogs):
        if existing.isVisible():
            existing.open_page(page)
            existing.raise_()
            existing.activateWindow()
            return

    dlg = SettingsDialog(window)
    dlg.setModal(False)
    dlg.setWindowFlag(Qt.Window, True)
    dlg.setAttribute(Qt.WA_DeleteOnClose, True)

    if hasattr(window, "apply_settings"):
        dlg.settings_changed.connect(window.apply_settings)
        dlg.finished.connect(lambda _: window.apply_settings())

    _open_dialogs.append(dlg)
    dlg.destroyed.connect(lambda: _open_dialogs.remove(dlg) if dlg in _open_dialogs else None)

    dlg.open_page(page)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
