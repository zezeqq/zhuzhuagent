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
    bootstrap_seed_data()

    from core.settings_runtime import apply_app_settings, check_skill_updates_on_startup
    from core.settings_runtime import reload_skill_handlers

    reload_skill_handlers()
    check_skill_updates_on_startup()

    window = MainWindow()
    apply_app_settings(app, window)

    from core.automation_scheduler import AutomationScheduler
    scheduler = AutomationScheduler(window)
    scheduler.automation_due.connect(lambda cid, _n, _p: window._on_automation_triggered(cid))
    scheduler.start()
    window._automation_scheduler = scheduler

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
