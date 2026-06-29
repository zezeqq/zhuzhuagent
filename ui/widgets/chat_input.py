from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QTextCursor
from PySide6.QtWidgets import QTextEdit


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".ico"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"}
ALLOWED_EXTS = IMAGE_EXTS | AUDIO_EXTS

_MENTION_DISPLAY_RE = re.compile(r"@\[([^\]]+)\]")


def format_mention_for_display(text: str) -> str:
    """Convert stored @[name] tokens to @name for message display."""
    return _MENTION_DISPLAY_RE.sub(r"@\1", text or "")


class ChatInputEdit(QTextEdit):
    """Chat input with drag-drop attachments and @ file reference trigger."""

    files_dropped = Signal(list)
    reference_trigger = Signal(str, QPoint)
    reference_cancel = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._ref_active = False
        self._ref_start = -1
        self.textChanged.connect(self._on_text_changed)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    suffix = Path(url.toLocalFile()).suffix.lower()
                    if suffix in ALLOWED_EXTS:
                        event.acceptProposedAction()
                        return
        if event.mimeData().hasImage():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        files: list[str] = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    fpath = url.toLocalFile()
                    suffix = Path(fpath).suffix.lower()
                    if suffix in ALLOWED_EXTS:
                        files.append(fpath)
        if event.mimeData().hasImage() and not files:
            img = QImage(event.mimeData().imageData())
            if not img.isNull():
                tmp = os.path.join(tempfile.gettempdir(), f"dna_paste_{id(img)}.png")
                img.save(tmp)
                files.append(tmp)
        if files:
            event.acceptProposedAction()
            self.files_dropped.emit(files)
        else:
            super().dropEvent(event)

    @staticmethod
    def _find_active_mention(text: str, pos: int) -> tuple[int, str] | None:
        """Return (at_index, query) when cursor is inside an open @ mention."""
        at = text.rfind("@", 0, pos)
        while at >= 0:
            if at > 0 and not text[at - 1].isspace():
                at = text.rfind("@", 0, at)
                continue

            segment = text[at + 1:pos]
            if not segment:
                return at, ""

            if segment.startswith("["):
                close = segment.find("]")
                if close >= 0:
                    # Completed @[name] token — not an active picker if cursor is after ']'
                    if pos > at + 1 + close + 1:
                        at = text.rfind("@", 0, at)
                        continue
                    return None
                return None

            if "\n" in segment:
                return None

            # Space at end of segment means user cancelled the open mention.
            if segment.endswith(" "):
                return None

            return at, segment

        return None

    def _cancel_reference_mode(self) -> None:
        if self._ref_active:
            self.reference_cancel.emit()
        self._ref_active = False
        self._ref_start = -1

    def _on_text_changed(self) -> None:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()[:pos]
        active = self._find_active_mention(text, pos)
        if not active:
            self._cancel_reference_mode()
            return

        at, query = active
        self._ref_active = True
        self._ref_start = at
        rect = self.cursorRect()
        global_pos = self.mapToGlobal(rect.bottomLeft())
        self.reference_trigger.emit(query, global_pos)

    def insert_file_reference(self, display_name: str) -> None:
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        start = self._ref_start if self._ref_start >= 0 else text.rfind("@", 0, pos)
        if start < 0:
            start = pos
            prefix = text[:pos]
            if not prefix.endswith("@"):
                prefix += "@"
        else:
            prefix = text[:start]
        suffix = text[pos:]
        mention = f"@[{display_name}] "
        new_text = prefix + mention + suffix.lstrip()
        cursor_pos = len(prefix + mention)
        self.blockSignals(True)
        self.setPlainText(new_text)
        cursor.setPosition(cursor_pos)
        self.setTextCursor(cursor)
        self.blockSignals(False)
        self._cancel_reference_mode()

    def trigger_reference_picker(self) -> None:
        cursor = self.textCursor()
        text = self.toPlainText()
        pos = cursor.position()
        before = text[:pos]
        after = text[pos:]
        if not before.endswith("@"):
            insert = "@" if (not before or before[-1].isspace()) else " @"
            new_text = before + insert + after
            pos = len(before + insert)
            self.setPlainText(new_text)
            cursor.setPosition(pos)
            self.setTextCursor(cursor)
        self._on_text_changed()
