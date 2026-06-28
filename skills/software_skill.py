import subprocess
from pathlib import Path


def open_software(executable_path: str, args: str = "", working_dir: str = "") -> str:
    if not executable_path:
        return "未配置可执行文件路径。"
    cmd = [executable_path] + ([args] if args else [])
    subprocess.Popen(cmd, cwd=working_dir or None)
    return "已尝试启动软件。"
