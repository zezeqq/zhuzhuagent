from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from db.database import insert, query_one


from utils.path_utils import installed_skills_dir, skill_downloads_dir

SKILL_ROOT = installed_skills_dir()
DOWNLOAD_DIR = skill_downloads_dir()


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if dest.resolve() != target and dest.resolve() not in target.parents:
                raise ValueError("压缩包包含不安全路径，已拒绝安装。")
        zf.extractall(dest)


def _download(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "DNA-Work-Agent/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        target.write_bytes(resp.read())
    return target


def _github_zip_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        return [url]
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if "archive" in parts:
        return [url]
    return [
        f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip",
        f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip",
    ]


def _find_manifest(root: Path) -> dict:
    for name in ["skill.json", "dna_skill.json", "manifest.json", "plugin.json"]:
        matches = list(root.rglob(name))
        if matches:
            return json.loads(matches[0].read_text(encoding="utf-8"))
    py_files = [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    display = root.name
    return {
        "name": display.lower().replace(" ", "_"),
        "display_name": display,
        "version": "0.1.0",
        "description": "从网络安装的本地 Skill 包。",
        "entry": str(py_files[0].relative_to(root)) if py_files else "",
    }


def _validate_tool_definitions(manifest: dict) -> None:
    """Validate that any ``tools`` declared in a manifest have the required fields."""
    tools = manifest.get("tools")
    if not tools:
        return
    if not isinstance(tools, list):
        raise ValueError("manifest 中 'tools' 字段必须是数组。")
    for idx, td in enumerate(tools):
        if not isinstance(td, dict):
            raise ValueError(f"tools[{idx}] 不是有效的 JSON 对象。")
        missing = [k for k in ("name", "description", "parameters") if not td.get(k)]
        if missing:
            raise ValueError(
                f"tools[{idx}] ('{td.get('name', '?')}') 缺少必需字段: {', '.join(missing)}"
            )
        params = td["parameters"]
        if not isinstance(params, dict) or params.get("type") != "object":
            raise ValueError(
                f"tools[{idx}] ('{td['name']}') 的 parameters 必须是 type=object 的 JSON Schema。"
            )


def install_skill_from_url(url: str) -> dict:
    if not url.strip():
        raise ValueError("请输入 Skill 下载地址或 GitHub 仓库地址。")
    SKILL_ROOT.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for candidate in _github_zip_candidates(url.strip()):
        try:
            suffix = ".zip" if candidate.lower().endswith(".zip") or "github.com" in candidate else Path(urlparse(candidate).path).suffix
            download_path = DOWNLOAD_DIR / f"skill_download{suffix or '.bin'}"
            _download(candidate, download_path)
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                if zipfile.is_zipfile(download_path):
                    _safe_extract_zip(download_path, tmp_path)
                    roots = [p for p in tmp_path.iterdir() if p.is_dir()]
                    package_root = roots[0] if len(roots) == 1 else tmp_path
                else:
                    package_root = tmp_path / download_path.name
                    shutil.copy2(download_path, package_root)
                manifest = _find_manifest(package_root if package_root.is_dir() else tmp_path)
                _validate_tool_definitions(manifest)
                package_name = manifest.get("name") or manifest.get("skill_name") or Path(urlparse(url).path).stem
                package_name = str(package_name).strip().replace(" ", "_")
                install_path = SKILL_ROOT / package_name
                if install_path.exists():
                    shutil.rmtree(install_path)
                if package_root.is_dir():
                    shutil.copytree(package_root, install_path)
                else:
                    install_path.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(package_root, install_path / package_root.name)
                _register_package(package_name, manifest, "url", url, install_path)
                from agent_runtime.skill_prompt_loader import ensure_skill_md
                ensure_skill_md(install_path, manifest)
                return {"package_name": package_name, "install_path": str(install_path), "manifest": manifest}
        except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as exc:
            last_error = str(exc)
    raise ValueError(f"安装失败：{last_error or '无法下载或识别 Skill 包'}")


def install_market_skill(
    skill_name: str,
    display_name: str,
    description: str = "",
    skill_md: str = "",
) -> dict:
    package_name = skill_name.strip().lower().replace(" ", "_")
    if not package_name:
        raise ValueError("Skill 名称不能为空。")
    install_path = SKILL_ROOT / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": package_name,
        "display_name": display_name,
        "version": "0.1.0",
        "description": description,
        "entry": "skill.py",
        "prompt_entry": "SKILL.md",
    }
    (install_path / "skill.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    from agent_runtime.skill_prompt_loader import default_skill_md

    md_content = skill_md.strip() or default_skill_md(display_name, description)
    (install_path / "SKILL.md").write_text(md_content, encoding="utf-8")
    (install_path / "skill.py").write_text(
        'def run(**kwargs):\n    return {"message": "Skill 已安装，请在后续版本中补充具体执行逻辑。", "input": kwargs}\n',
        encoding="utf-8",
    )
    _register_package(package_name, manifest, "market", "", install_path)
    return {"package_name": package_name, "install_path": str(install_path), "manifest": manifest}


def _register_package(package_name: str, manifest: dict, source_type: str, source_url: str, install_path: Path) -> None:
    existing = query_one("SELECT id FROM installed_skill_packages WHERE package_name=?", (package_name,))
    data = {
        "package_name": package_name,
        "display_name": manifest.get("display_name") or package_name,
        "version": str(manifest.get("version") or "0.1.0"),
        "source_type": source_type,
        "source_url": source_url,
        "install_path": str(install_path),
        "manifest_json": json.dumps(manifest, ensure_ascii=False),
        "enabled": 1,
    }
    if existing:
        from db.database import execute

        execute(
            "UPDATE installed_skill_packages SET display_name=?, version=?, source_type=?, source_url=?, install_path=?, manifest_json=?, enabled=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (
                data["display_name"],
                data["version"],
                data["source_type"],
                data["source_url"],
                data["install_path"],
                data["manifest_json"],
                existing["id"],
            ),
        )
    else:
        insert("installed_skill_packages", data)
