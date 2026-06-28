from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from db.database import execute, insert, query_all, query_one


COMMON_EXECUTABLES = {
    "VS Code": ["code", "Code.exe"],
    "PyCharm": ["pycharm64.exe", "pycharm.exe"],
    "Chrome": ["chrome", "chrome.exe"],
    "Edge": ["msedge", "msedge.exe"],
    "Word": ["WINWORD.EXE"],
    "Excel": ["EXCEL.EXE"],
    "PowerPoint": ["POWERPNT.EXE"],
    "Git": ["git", "git.exe"],
    "Windows Terminal": ["wt", "wt.exe"],
}

COMMON_DIRS = [
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path.home() / "AppData/Local/Programs",
    Path.home() / "AppData/Local",
]

KNOWN_PATHS = {
    "VS Code": [
        Path.home() / "AppData/Local/Programs/Microsoft VS Code/Code.exe",
        Path("C:/Program Files/Microsoft VS Code/Code.exe"),
    ],
    "PyCharm": [
        Path("C:/Program Files/JetBrains/PyCharm Community Edition 2024.3/bin/pycharm64.exe"),
        Path("C:/Program Files/JetBrains/PyCharm 2024.3/bin/pycharm64.exe"),
        Path("C:/Program Files/JetBrains/PyCharm 2025.1/bin/pycharm64.exe"),
    ],
    "Chrome": [Path("C:/Program Files/Google/Chrome/Application/chrome.exe")],
    "Edge": [Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")],
    "Word": [Path("C:/Program Files/Microsoft Office/root/Office16/WINWORD.EXE")],
    "Excel": [Path("C:/Program Files/Microsoft Office/root/Office16/EXCEL.EXE")],
    "PowerPoint": [Path("C:/Program Files/Microsoft Office/root/Office16/POWERPNT.EXE")],
}


def find_executable(software_name: str) -> str:
    candidates = COMMON_EXECUTABLES.get(software_name, [software_name])
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    for path in KNOWN_PATHS.get(software_name, []):
        if path.exists():
            return str(path)
    return ""


def auto_detect_software() -> list[dict]:
    results = []
    for software_name in COMMON_EXECUTABLES:
        path = find_executable(software_name)
        if not path:
            continue
        row = query_one("SELECT id FROM software_tools WHERE software_name=?", (software_name,))
        data = {
            "software_name": software_name,
            "software_type": "detected",
            "executable_path": path,
            "enabled": 1,
            "remark": "自动检测到的本机软件",
        }
        if row:
            execute(
                "UPDATE software_tools SET software_type=?, executable_path=?, enabled=1, remark=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (data["software_type"], data["executable_path"], data["remark"], row["id"]),
            )
        else:
            insert("software_tools", data)
        results.append(data)
    return results


def launch_software(software_id: int, extra_args: str = "", open_path: str = "") -> str:
    row = query_one("SELECT * FROM software_tools WHERE id=?", (software_id,))
    if not row:
        raise ValueError("软件配置不存在。")
    executable = row.get("executable_path") or ""
    if not executable:
        raise ValueError("请先配置该软件的可执行文件路径。")
    cmd = [executable]
    launch_args = row.get("launch_args") or ""
    if launch_args:
        cmd.extend(shlex.split(launch_args))
    if extra_args:
        cmd.extend(shlex.split(extra_args))
    if open_path:
        cmd.append(open_path)
    subprocess.Popen(cmd, cwd=row.get("working_dir") or None)
    insert(
        "software_actions",
        {
            "software_id": software_id,
            "action_name": "launch",
            "input_json": str({"cmd": cmd, "open_path": open_path}),
            "status": "completed",
        },
    )
    return f"已启动：{row.get('software_name')}"


def configured_software() -> list[dict]:
    return query_all("SELECT * FROM software_tools ORDER BY enabled DESC, software_name")
