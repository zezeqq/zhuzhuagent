import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from core.app_identity import APP_NAME
from core.bootstrap import bootstrap_seed_data
from db.database import init_database
from ui.main_window import MainWindow
from utils.logger import setup_logger


def excepthook(exc_type, exc_value, exc_tb):
    message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger = setup_logger()
    logger.error("Unhandled error: %s", message)
    QMessageBox.critical(None, f"{APP_NAME} 运行错误", message[:3000])


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    sys.excepthook = excepthook
    logger = setup_logger()
    from utils.path_utils import app_root, data_dir, is_frozen
    logger.info("%s starting (frozen=%s, root=%s, data=%s)", APP_NAME, is_frozen(), app_root(), data_dir())
    init_database()

    from core.settings_runtime import apply_app_settings
    from core.settings_store import get_bool

    apply_app_settings(app)
    window = MainWindow()
    apply_app_settings(app, window, startup=True, apply_theme=False)
    window.show()

    import threading
    from PySide6.QtCore import QTimer

    def _deferred_startup() -> None:
        try:
            bootstrap_seed_data()
            from core.settings_runtime import reload_skill_handlers, check_skill_updates_on_startup
            reload_skill_handlers()
            check_skill_updates_on_startup()
        except Exception as exc:
            logger.warning("Deferred startup failed: %s", exc)

    threading.Thread(target=_deferred_startup, daemon=True, name="DeferredStartup").start()

    if get_bool("enable_mcp", True):
        try:
            import mcp  # noqa: F401
        except ImportError:
            logger.warning("MCP SDK missing in this venv — run: pip install mcp")
            QMessageBox.warning(
                None,
                f"{APP_NAME} — MCP",
                "当前 Python 环境未安装 MCP SDK，MCP 工具不可用。\n\n"
                "请在项目虚拟环境中执行：\n"
                "  pip install mcp\n\n"
                "或：pip install -r requirements.txt",
            )

    from core.automation_scheduler import AutomationScheduler
    scheduler = AutomationScheduler(window)
    scheduler.automation_due.connect(lambda cid, _n, _p: window._on_automation_triggered(cid))
    scheduler.start()
    window._automation_scheduler = scheduler

    from agent_runtime.mcp_client import ensure_mcp_tools_loaded, get_mcp_status_summary, mcp_enabled

    def _mcp_startup() -> None:
        if not mcp_enabled():
            return
        msg = ensure_mcp_tools_loaded()
        summary = get_mcp_status_summary()
        logger.info("MCP startup: %s | tools=%s connected=%s", msg, summary.get("tool_count"), summary.get("connected"))

    QTimer.singleShot(1200, lambda: threading.Thread(target=_mcp_startup, daemon=True, name="MCPStartup").start())

    def _warm_file_tree() -> None:
        try:
            if window._results._files_stale:
                window._results.refresh_files()
        except Exception:
            pass

    QTimer.singleShot(2500, _warm_file_tree)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
