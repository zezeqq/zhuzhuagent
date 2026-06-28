"""动态解析本机已安装应用，不依赖硬编码软件别名表。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# 仅 Windows 内置程序：系统命令名与 exe 的固定映射
_SYSTEM_APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "记事本": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "计算器": "calc.exe",
    "mspaint": "mspaint.exe",
    "paint": "mspaint.exe",
    "画图": "mspaint.exe",
    "explorer": "explorer.exe",
    "文件管理器": "explorer.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "taskmgr": "Taskmgr.exe",
    "任务管理器": "Taskmgr.exe",
    "wt": "wt.exe",
    "terminal": "wt.exe",
    "终端": "wt.exe",
}

_SKIP_EXE_STEMS = frozenset({
    "uninstall", "uninst", "update", "updater", "crash", "helper",
    "setup", "install", "launcher", "elevate", "feedback",
})

_exe_cache: dict[str, str | None] = {}


@dataclass
class AppMatch:
    path: str
    source: str
    label: str
    score: float


def generate_search_terms(name: str) -> list[str]:
    """从用户/模型给出的名称生成多种检索关键词。"""
    raw = name.strip()
    if not raw:
        return []

    terms = [raw]
    compact = raw.replace(" ", "")
    if compact != raw:
        terms.append(compact)

    for suffix in ("音乐", "播放器", "客户端", "Desktop", "desktop", "音乐版"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            terms.append(raw[: -len(suffix)].strip())

    if raw.isascii():
        parts = re.split(r"[\s\-_]+", raw)
        if len(parts) > 1:
            terms.append("".join(parts))
            terms.append("".join(p.capitalize() for p in parts))

    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def generate_exe_candidates(name: str) -> list[str]:
    """生成可能的 exe 文件名（不写死具体软件）。"""
    terms = generate_search_terms(name)
    cands: list[str] = []
    for t in terms:
        cands.append(f"{t}.exe")
        if t.lower().endswith(".exe"):
            cands.append(t)
        if t.isascii():
            cands.append(f"{t.lower()}.exe")
            titled = t.title().replace(" ", "")
            cands.append(f"{titled}.exe")
    return list(dict.fromkeys(cands))


def _score_match(query: str, text: str) -> float:
    q = query.strip().lower()
    t = text.strip().lower()
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if q in t or t in q:
        return 0.85
    # 共享连续子串（>=2 字符）
    best = 0
    for i in range(len(q)):
        for j in range(i + 2, len(q) + 1):
            sub = q[i:j]
            if sub in t:
                best = max(best, len(sub) / max(len(q), len(t)))
    return best * 0.75


def _pick_main_exe(folder: Path, hint: str = "") -> Path | None:
    """在目录中挑选最像主程序的 exe。"""
    try:
        exes = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".exe"]
    except (PermissionError, OSError):
        return None
    if not exes:
        return None

    hint_low = hint.lower()
    folder_low = folder.name.lower()

    def rank(p: Path) -> tuple:
        stem = p.stem.lower()
        skip = stem in _SKIP_EXE_STEMS or any(s in stem for s in _SKIP_EXE_STEMS)
        name_match = (
            hint_low in stem or stem in hint_low
            or folder_low in stem or stem in folder_low
        )
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        return (0 if skip else 1, 1 if name_match else 0, size)

    exes.sort(key=rank, reverse=True)
    for exe in exes:
        if rank(exe)[0] == 1:
            return exe
    return None


def _search_registry(terms: list[str], exe_candidates: list[str]) -> list[AppMatch]:
    import winreg

    matches: list[AppMatch] = []
    seen: set[str] = set()

    reg_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, base_path in reg_roots:
        try:
            base_key = winreg.OpenKey(hive, base_path)
        except OSError:
            continue
        try:
            idx = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(base_key, idx)
                    idx += 1
                except OSError:
                    break
                try:
                    sub_key = winreg.OpenKey(base_key, sub_name)
                except OSError:
                    continue
                try:
                    display = ""
                    try:
                        display, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                    except OSError:
                        pass
                    display = str(display)
                    sub_low = sub_name.lower()
                    best = max(
                        (_score_match(t, display) for t in terms),
                        default=0.0,
                    )
                    best = max(best, max(_score_match(t, sub_low) for t in terms))
                    if best < 0.35:
                        winreg.CloseKey(sub_key)
                        continue

                    exe_path: Path | None = None
                    for val_name in ("DisplayIcon", "InstallLocation"):
                        try:
                            val, _ = winreg.QueryValueEx(sub_key, val_name)
                            val = str(val).strip().strip('"').split(",")[0]
                        except OSError:
                            continue
                        if not val:
                            continue
                        p = Path(val)
                        if p.is_file() and p.suffix.lower() == ".exe":
                            exe_path = p
                            break
                        if p.is_dir():
                            for c in exe_candidates:
                                cand = p / c
                                if cand.is_file():
                                    exe_path = cand
                                    break
                            if exe_path is None:
                                exe_path = _pick_main_exe(p, display or sub_name)
                        if exe_path:
                            break

                    if exe_path and exe_path.is_file():
                        key = str(exe_path).lower()
                        if key not in seen:
                            seen.add(key)
                            matches.append(AppMatch(
                                path=str(exe_path),
                                source="registry",
                                label=display or sub_name,
                                score=best,
                            ))
                finally:
                    winreg.CloseKey(sub_key)
        finally:
            winreg.CloseKey(base_key)

    return matches


def _search_start_menu(terms: list[str]) -> list[AppMatch]:
    """通过 PowerShell Get-StartApps 检索开始菜单应用。"""
    matches: list[AppMatch] = []
    seen: set[str] = set()
    for term in terms[:4]:
        if len(term) < 2:
            continue
        safe = term.replace("'", "''")
        ps = (
            f"Get-StartApps | Where-Object {{ $_.Name -like '*{safe}*' }} "
            f"| Select-Object -First 12 Name, AppID | ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0 or not result.stdout.strip():
                continue
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                app_name = str(item.get("Name", ""))
                app_id = str(item.get("AppID", ""))
                if not app_name:
                    continue
                score = max(_score_match(t, app_name) for t in terms)
                key = app_name.lower()
                if key in seen:
                    continue
                seen.add(key)
                matches.append(AppMatch(
                    path=app_id,
                    source="start_menu",
                    label=app_name,
                    score=score,
                ))
        except Exception:
            continue
    return matches


def _search_directories(terms: list[str], exe_candidates: list[str]) -> list[AppMatch]:
    matches: list[AppMatch] = []
    seen: set[str] = set()
    bases: list[Path] = []
    for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
        val = os.environ.get(env_var)
        if val and Path(val).is_dir():
            bases.append(Path(val))

    for base in bases:
        try:
            subs = list(base.iterdir())
        except (PermissionError, OSError):
            continue
        for sub in subs:
            if not sub.is_dir():
                continue
            folder_name = sub.name
            folder_low = folder_name.lower()
            best = max(_score_match(t, folder_name) for t in terms)
            if best < 0.4:
                continue

            exe: Path | None = None
            for c in exe_candidates:
                cand = sub / c
                if cand.is_file():
                    exe = cand
                    break
            if exe is None:
                exe = _pick_main_exe(sub, terms[0] if terms else folder_name)
            if exe and exe.is_file():
                key = str(exe).lower()
                if key not in seen:
                    seen.add(key)
                    matches.append(AppMatch(
                        path=str(exe),
                        source="install_dir",
                        label=folder_name,
                        score=best,
                    ))
            else:
                try:
                    for deep in sub.iterdir():
                        if not deep.is_dir():
                            continue
                        if max(_score_match(t, deep.name) for t in terms) < 0.5:
                            continue
                        inner = _pick_main_exe(deep, terms[0] if terms else deep.name)
                        if inner and inner.is_file():
                            key = str(inner).lower()
                            if key not in seen:
                                seen.add(key)
                                matches.append(AppMatch(
                                    path=str(inner),
                                    source="install_dir",
                                    label=f"{folder_name}/{deep.name}",
                                    score=best,
                                ))
                except (PermissionError, OSError):
                    pass

    return matches


def _search_path(exe_candidates: list[str]) -> list[AppMatch]:
    matches: list[AppMatch] = []
    for cand in exe_candidates:
        try:
            result = subprocess.run(
                ["where", cand],
                capture_output=True, text=True, timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                found = result.stdout.strip().splitlines()[0]
                if found and Path(found).is_file():
                    matches.append(AppMatch(
                        path=found, source="path", label=cand, score=0.7,
                    ))
                    break
        except Exception:
            continue
    return matches


def resolve_application(name: str, *, limit: int = 8) -> list[AppMatch]:
    """综合注册表、开始菜单、安装目录、PATH 动态查找应用。"""
    terms = generate_search_terms(name)
    if not terms:
        return []

    exe_candidates = generate_exe_candidates(name)
    all_matches: list[AppMatch] = []

    all_matches.extend(_search_path(exe_candidates))
    all_matches.extend(_search_registry(terms, exe_candidates))
    all_matches.extend(_search_start_menu(terms))
    all_matches.extend(_search_directories(terms, exe_candidates))

    # 去重并按分数排序
    by_path: dict[str, AppMatch] = {}
    for m in all_matches:
        key = m.path.lower()
        if key not in by_path or m.score > by_path[key].score:
            by_path[key] = m

    ranked = sorted(by_path.values(), key=lambda x: x.score, reverse=True)
    return ranked[:limit]


def find_best_executable(name: str) -> tuple[str | None, str]:
    """返回 (exe路径, 说明)。路径为 start_menu 的 AppID 时由调用方处理。"""
    key = name.strip().lower()
    if key in _exe_cache:
        cached = _exe_cache[key]
        if cached and (Path(cached).is_file() or cached.startswith("shell:")):
            return cached, "cache"
        if cached is None:
            return None, "未找到"

    sys_exe = _SYSTEM_APPS.get(key)
    if sys_exe:
        _exe_cache[key] = sys_exe
        return sys_exe, f"系统程序 ({sys_exe})"

    if Path(name).is_file():
        _exe_cache[key] = name
        return name, "用户指定路径"

    matches = resolve_application(name, limit=8)
    file_matches = [m for m in matches if Path(m.path).is_file()]
    if file_matches:
        best = file_matches[0]
        _exe_cache[key] = best.path
        return best.path, f"{best.source}: {best.label} → {best.path}"

    for m in matches:
        if m.source == "start_menu":
            _exe_cache[key] = m.path
            return m.path, f"开始菜单: {m.label} ({m.path})"

    _exe_cache[key] = None
    return None, "未找到"


def format_matches_for_agent(name: str, matches: list[AppMatch]) -> str:
    if not matches:
        terms = ", ".join(generate_search_terms(name))
        return (
            f"未找到与「{name}」匹配的本机应用。\n"
            f"已尝试检索关键词: {terms}\n"
            "建议：换用英文名/全称再试，或提供 exe 完整路径。"
        )
    lines = [f"找到 {len(matches)} 个与「{name}」可能匹配的应用："]
    for i, m in enumerate(matches, 1):
        lines.append(f"{i}. [{m.source}] {m.label}")
        lines.append(f"   路径/AppID: {m.path}")
        lines.append(f"   匹配度: {m.score * 100:.0f}%")
    lines.append("\n可用 software_launch 传入上述路径，或用更精确的名称启动。")
    return "\n".join(lines)


def launch_match(path_or_id: str, label: str = "") -> str:
    """启动 exe 或开始菜单 AppID。"""
    p = Path(path_or_id)
    if p.is_file():
        os.startfile(str(p))
        return f"已启动: {label or p.name} ({p})"

    safe_id = path_or_id.replace("'", "''")
    for cmd in (
        ["explorer.exe", f"shell:AppsFolder\\{path_or_id}"],
        ["powershell", "-NoProfile", "-Command", f"Start-Process '{safe_id}'"],
    ):
        try:
            subprocess.Popen(
                cmd,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return f"已启动: {label or path_or_id}"
        except Exception:
            continue
    return f"无法启动: {path_or_id}"
