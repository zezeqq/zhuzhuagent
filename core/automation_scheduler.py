"""自动化定时调度：应用运行时每分钟检查，到点则触发会话。"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from core.conversation_manager import add_message, create_conversation
from core.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)

_WEEKDAY_MAP = {
    "mon": 0, "monday": 0, "一": 0, "周一": 0,
    "tue": 1, "tuesday": 1, "二": 1, "周二": 1,
    "wed": 2, "wednesday": 2, "三": 2, "周三": 2,
    "thu": 3, "thursday": 3, "四": 3, "周四": 3,
    "fri": 4, "friday": 4, "五": 4, "周五": 4,
    "sat": 5, "saturday": 5, "六": 5, "周六": 5,
    "sun": 6, "sunday": 6, "日": 6, "周日": 6, "星期天": 6,
}


def load_scheduled_automations() -> list[dict]:
    raw = get_setting("automations", "[]")
    try:
        items = json.loads(raw)
        if isinstance(items, list):
            return items
    except Exception:
        pass
    return []


def save_scheduled_automations(items: list[dict]) -> None:
    set_setting("automations", json.dumps(items, ensure_ascii=False), "json")


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    parts = (value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _should_fire(entry: dict, now: datetime) -> bool:
    if not entry.get("enabled", True):
        return False
    sched = entry.get("schedule") or {}
    stype = sched.get("type", "manual")
    if stype in ("manual", "once", ""):
        return False
    hhmm = _parse_hhmm(sched.get("time", "09:00"))
    if not hhmm:
        return False
    hour, minute = hhmm
    if now.hour != hour or now.minute != minute:
        return False
    if stype == "daily":
        return True
    if stype == "weekly":
        target = sched.get("weekday", 6)
        if isinstance(target, str):
            target = _WEEKDAY_MAP.get(target.lower(), 6)
        return now.weekday() == int(target)
    return False


class AutomationScheduler(QObject):
    """到点创建会话并通知主窗口 replay。"""

    automation_due = Signal(int, str, str)  # conv_id, name, prompt

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._tick)
        self._last_fired: dict[str, str] = {}

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(5000, self._tick)

    def _tick(self) -> None:
        now = datetime.now()
        slot_key = now.strftime("%Y-%m-%d %H:%M")
        items = load_scheduled_automations()
        changed = False
        for i, entry in enumerate(items):
            if not _should_fire(entry, now):
                continue
            uid = entry.get("id") or f"auto_{i}"
            if self._last_fired.get(uid) == slot_key:
                continue
            name = entry.get("name", "自动化")
            prompt = entry.get("prompt", "")
            user_text = f"[定时自动化] {name}\n\n{prompt}"
            conv_id = create_conversation(title=name)
            add_message(conv_id, "user", user_text)
            entry["last_run"] = now.isoformat(timespec="seconds")
            self._last_fired[uid] = slot_key
            changed = True
            logger.info("Automation fired: %s conv=%s", name, conv_id)
            self.automation_due.emit(conv_id, name, prompt)
        if changed:
            save_scheduled_automations(items)
