from pathlib import Path
import shutil


def copy_to_folder(source: str | Path, target_folder: str | Path) -> Path:
    source_path = Path(source)
    target = Path(target_folder) / source_path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        stem, suffix = target.stem, target.suffix
        index = 1
        while target.exists():
            target = target.parent / f"{stem}_{index}{suffix}"
            index += 1
    shutil.copy2(source_path, target)
    return target
