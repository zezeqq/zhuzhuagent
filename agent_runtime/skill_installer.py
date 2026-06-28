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

from agent_runtime.skill_package_detect import (
    apply_prompt_entry_to_manifest,
    find_skill_package_roots,
)
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


def _find_skill_package_roots(root: Path) -> list[Path]:
    """识别可安装的 Skill 包目录（支持 SKILL.md / 任意 md / .claude/skills 等）。"""
    return find_skill_package_roots(root)


def _readme_excerpt(root: Path, max_chars: int = 8000) -> str:
    for name in ("README.md", "Readme.md", "readme.md"):
        p = root / name
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")[:max_chars]
    return ""


def _find_manifest(root: Path) -> dict:
    for name in ["skill.json", "dna_skill.json", "manifest.json", "plugin.json"]:
        matches = list(root.rglob(name))
        if matches:
            return json.loads(matches[0].read_text(encoding="utf-8"))
    py_files = [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    display = root.name
    readme = _readme_excerpt(root)
    return {
        "name": display.lower().replace(" ", "_"),
        "display_name": display,
        "version": "0.1.0",
        "description": readme[:500] if readme else "从网络安装的本地 Skill 包。",
        "entry": str(py_files[0].relative_to(root)).replace("\\", "/") if py_files else "",
    }


def describe_github_install_compat(source_url: str = "") -> str:
    """说明 GitHub 仓库与 Buddy Skill 模型的差异（供 UI 展示）。"""
    return (
        "Buddy 的 Skill = 目录里的 Markdown 说明注入 Agent 对话（类似 Cursor Agent Skill）。\n"
        "GitHub 上的技能仓库常见结构：\n"
        "· skills/名称/SKILL.md 或 .claude/skills/名称/SKILL.md\n"
        "· 说明文件也可叫其他名字（如 aass.md），manifest 里 prompt_entry 指向即可\n"
        "· scripts、hooks 供 Claude Code / Cursor 使用，Buddy 不会自动执行\n\n"
        "安装时会扫描 skills、.claude/skills 等目录下的子包；"
        "每个包按 manifest 或目录内 md 识别，多个子 Skill 会批量安装。\n"
        "若整个仓库没有可识别的 Skill 包，会用 README 生成简易说明，效果有限。"
    )


def _manifest_for_package(package_root: Path) -> dict:
    for name in ["skill.json", "dna_skill.json", "manifest.json", "plugin.json"]:
        p = package_root / name
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return _find_manifest(package_root)


def _install_package_tree(package_root: Path, source_url: str) -> dict:
    manifest = _manifest_for_package(package_root)
    manifest = apply_prompt_entry_to_manifest(package_root, manifest)
    _validate_tool_definitions(manifest)
    package_name = (
        manifest.get("name")
        or manifest.get("skill_name")
        or package_root.name
    )
    package_name = str(package_name).strip().lower().replace(" ", "_")
    if not package_name:
        raise ValueError("无法确定 Skill 包名称。")

    install_path = SKILL_ROOT / package_name
    if install_path.exists():
        shutil.rmtree(install_path)
    shutil.copytree(package_root, install_path)

    if not manifest.get("display_name"):
        manifest["display_name"] = manifest.get("name") or package_root.name
    manifest.setdefault("skill_type", "prompt")
    manifest.setdefault("prompt_entry", "SKILL.md")

    _register_package(package_name, manifest, "url", source_url, install_path)
    from agent_runtime.skill_prompt_loader import ensure_skill_md

    ensure_skill_md(install_path, manifest)
    return {
        "package_name": package_name,
        "install_path": str(install_path),
        "manifest": manifest,
    }


def _validate_tool_definitions(manifest: dict) -> None:
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


def _manifest_from_catalog(skill: dict) -> dict:
    package_name = skill["name"].strip().lower().replace(" ", "_")
    manifest: dict = {
        "name": package_name,
        "display_name": skill.get("display") or package_name,
        "version": "0.1.0",
        "description": skill.get("desc", ""),
        "skill_type": skill.get("skill_type", "prompt"),
        "prompt_entry": "SKILL.md",
    }
    if skill.get("tools"):
        manifest["entry"] = "skill.py"
        manifest["tools"] = skill["tools"]
    else:
        manifest["entry"] = "skill.py"
    if skill.get("recommended_mcp"):
        manifest["recommended_mcp"] = list(skill["recommended_mcp"])
    if skill.get("recommended_tools"):
        manifest["recommended_tools"] = list(skill["recommended_tools"])
    return manifest


def install_from_catalog(skill: dict) -> dict:
    """Install a skill from unified catalog entry."""
    from core.skill_catalog import is_planned_skill

    if is_planned_skill(skill):
        raise ValueError(f"「{skill.get('display', skill.get('name'))}」尚在规划中，暂不可安装。")
    return install_market_skill(
        skill["name"],
        skill.get("display") or skill["name"],
        skill.get("desc", ""),
        skill_md=skill.get("skill_md", ""),
        catalog_entry=skill,
    )


def refresh_installed_bundled_skills() -> list[str]:
    """已安装的内置 Skill 若 catalog 版本更新，重写 SKILL.md 与 manifest。"""
    from core.remote_catalog import _load_bundled_catalog_skills
    from db.database import query_all

    updated: list[str] = []
    bundled = {s["name"]: s for s in _load_bundled_catalog_skills()}
    for row in query_all(
        "SELECT package_name, install_path, manifest_json FROM installed_skill_packages WHERE enabled=1"
    ):
        pkg = row.get("package_name") or ""
        if pkg not in bundled:
            continue
        src = bundled[pkg]
        install_path = Path(row.get("install_path") or "")
        if not install_path.is_dir():
            continue
        md = (src.get("skill_md") or "").strip()
        if md:
            (install_path / "SKILL.md").write_text(md, encoding="utf-8")
        manifest = _manifest_from_catalog(src)
        (install_path / "skill.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if src.get("tools"):
            from agent_runtime.skill_tool_scaffold import default_tool_skill_py
            (install_path / "skill.py").write_text(
                default_tool_skill_py(pkg, src["tools"]), encoding="utf-8"
            )
        _register_package(pkg, manifest, "market", "", install_path)
        updated.append(src.get("display") or pkg)
    return updated


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
                    repo_root = roots[0] if len(roots) == 1 else tmp_path
                else:
                    repo_root = tmp_path / download_path.name
                    shutil.copy2(download_path, repo_root)

                if not repo_root.is_dir():
                    raise ValueError("无法识别解压后的 Skill 目录。")

                package_roots = _find_skill_package_roots(repo_root)
                if not package_roots:
                    result = _install_package_tree(repo_root, url.strip())
                    result["install_mode"] = "repo_fallback"
                    return result

                installed: list[dict] = []
                for pkg_root in package_roots:
                    installed.append(_install_package_tree(pkg_root, url.strip()))

                primary = installed[0]
                primary["install_mode"] = "skill_md" if len(installed) == 1 else "batch"
                if len(installed) > 1:
                    primary["batch_installed"] = len(installed)
                    primary["packages"] = [r["package_name"] for r in installed]
                return primary
        except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as exc:
            last_error = str(exc)
    raise ValueError(f"安装失败：{last_error or '无法下载或识别 Skill 包'}")


def install_market_skill(
    skill_name: str,
    display_name: str,
    description: str = "",
    skill_md: str = "",
    *,
    catalog_entry: dict | None = None,
) -> dict:
    catalog_entry = catalog_entry or {}
    package_name = skill_name.strip().lower().replace(" ", "_")
    if not package_name:
        raise ValueError("Skill 名称不能为空。")
    install_path = SKILL_ROOT / package_name
    install_path.mkdir(parents=True, exist_ok=True)

    skill_type = catalog_entry.get("skill_type", "prompt")
    tools = catalog_entry.get("tools") or []
    manifest = _manifest_from_catalog({
        "name": package_name,
        "display": display_name,
        "desc": description,
        "skill_type": skill_type,
        "tools": tools,
        "recommended_mcp": catalog_entry.get("recommended_mcp"),
        "recommended_tools": catalog_entry.get("recommended_tools"),
    })

    from agent_runtime.skill_prompt_loader import default_skill_md
    from agent_runtime.skill_tool_scaffold import default_tool_skill_py

    md_content = skill_md.strip() or default_skill_md(display_name, description)
    (install_path / "SKILL.md").write_text(md_content, encoding="utf-8")
    (install_path / "skill.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if tools:
        py_content = default_tool_skill_py(package_name, tools)
        (install_path / "skill.py").write_text(py_content, encoding="utf-8")
    else:
        (install_path / "skill.py").write_text(
            'def handle(args: dict) -> str:\n'
            '    return "本 Skill 为说明文档型（prompt），请通过 SKILL.md 指导 Agent 使用内置/MCP 工具。"\n',
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
