from __future__ import annotations

from datetime import datetime
from pathlib import Path


TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".sql",
}


def resolve_project_file(project_folder: str, relative_path: str) -> Path:
    if not project_folder:
        raise ValueError("请先选择项目目录。")
    if not relative_path:
        raise ValueError("请填写项目内相对文件路径。")
    root = Path(project_folder).expanduser().resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("目标文件必须位于项目目录内部。")
    return target


def write_project_file(project_folder: str, relative_path: str, content: str, create_backup: bool = True) -> Path:
    target = resolve_project_file(project_folder, relative_path)
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError(f"暂只允许写入文本/代码文件，当前扩展名：{target.suffix or '无'}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and create_backup:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = target.with_name(f"{target.name}.{stamp}.bak")
        backup.write_bytes(target.read_bytes())
    target.write_text(content, encoding="utf-8")
    return target


def list_project_tree(project_folder: str, max_files: int = 120) -> list[str]:
    root = Path(project_folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return []
    ignored = {".git", ".idea", ".venv", "venv", "__pycache__", "node_modules", "dist", "build"}
    files: list[str] = []
    for path in root.rglob("*"):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file():
            files.append(str(path.relative_to(root)))
        if len(files) >= max_files:
            break
    return files
