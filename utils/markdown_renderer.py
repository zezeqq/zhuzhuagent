from __future__ import annotations

import html
import re


def _md_colors() -> dict[str, str]:
    from ui.theme import Palette
    return {
        "text": Palette.TEXT,
        "muted": Palette.MUTED,
        "weak": Palette.WEAK,
        "border": Palette.BORDER,
        "card": Palette.CARD,
        "card_alt": Palette.SURFACE if hasattr(Palette, "SURFACE") else Palette.CARD_HOVER,
        "input": Palette.INPUT,
        "toolbar": Palette.TOOLBAR,
        "blue": Palette.BLUE,
        "warning": Palette.WARNING,
        "body": Palette.MUTED,
    }


def markdown_to_html(text: str) -> str:
    """Convert markdown text to styled HTML for QTextBrowser display."""
    if not text:
        return ""

    text = _normalize_newlines(text)
    blocks = _split_blocks(text)
    html_parts: list[str] = []

    for block in blocks:
        if block.startswith("```"):
            html_parts.append(_render_code_block(block))
        elif _is_table(block):
            html_parts.append(_render_table(block))
        elif block.startswith("#"):
            html_parts.append(_render_heading(block))
        elif block.startswith(("- ", "* ", "+ ")):
            html_parts.append(_render_unordered_list(block))
        elif re.match(r"^\d+\.\s", block):
            html_parts.append(_render_ordered_list(block))
        elif block.startswith("> "):
            html_parts.append(_render_blockquote(block))
        elif block.startswith("---") and block.strip().replace("-", "") == "":
            html_parts.append("<hr/>")
        else:
            html_parts.append(_render_paragraph(block))

    body = "\n".join(html_parts)
    return f"{_CSS_STYLE}\n{body}"


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_blocks(text: str) -> list[str]:
    """Split text into logical blocks (paragraphs, code blocks, etc.)."""
    blocks: list[str] = []
    lines = text.split("\n")
    current: list[str] = []
    in_code = False

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                current.append(line)
                blocks.append("\n".join(current))
                current = []
                in_code = False
            else:
                if current:
                    blocks.append("\n".join(current))
                    current = []
                current.append(line)
                in_code = True
        elif in_code:
            current.append(line)
        elif line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        elif line.strip().startswith("#"):
            if current:
                blocks.append("\n".join(current))
                current = []
            blocks.append(line)
        elif line.strip().startswith("---") and not line.strip().replace("-", "").strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            blocks.append(line)
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current))

    return [b for b in blocks if b.strip()]


def _is_table(block: str) -> bool:
    lines = block.strip().split("\n")
    if len(lines) < 2:
        return False
    return "|" in lines[0] and re.match(r"^\s*\|?[\s\-:|]+\|", lines[1])


def _render_heading(block: str) -> str:
    c = _md_colors()
    line = block.split("\n")[0]
    level = 0
    for ch in line:
        if ch == "#":
            level += 1
        else:
            break
    level = min(level, 6)
    text = _inline_format(html.escape(line.lstrip("# ").strip()))
    sizes = {1: "22px", 2: "19px", 3: "17px", 4: "15px", 5: "14px", 6: "14px"}
    weights = {1: "800", 2: "750", 3: "700", 4: "650", 5: "650", 6: "600"}
    size = sizes.get(level, "15px")
    weight = weights.get(level, "600")
    color = c["text"] if level <= 2 else c["body"]
    margin = "16px 0 8px 0" if level <= 2 else "12px 0 6px 0"
    border = f"border-bottom: 1px solid {c['border']}; padding-bottom: 6px;" if level <= 2 else ""
    return f'<div style="font-size:{size}; font-weight:{weight}; color:{color}; margin:{margin}; letter-spacing:0; {border}">{text}</div>'


def _render_code_block(block: str) -> str:
    c = _md_colors()
    lines = block.split("\n")
    lang = lines[0].strip().lstrip("`").strip() if lines else ""
    code_lines = lines[1:-1] if len(lines) > 2 and lines[-1].strip().startswith("```") else lines[1:]
    code = html.escape("\n".join(code_lines))
    lang_badge = f'<span style="color:{c["weak"]}; font-size:11px; float:right;">{html.escape(lang)}</span>' if lang else ""
    return (
        f'<div style="background-color:{c["input"]}; border:1px solid {c["border"]}; border-radius:12px; '
        f'padding:13px 15px; margin:10px 0; font-family:Cascadia Mono,Consolas,monospace; '
        f'font-size:12px; color:{c["text"]}; line-height:1.6; white-space:pre-wrap; overflow-x:auto;">'
        f'{lang_badge}<code>{code}</code></div>'
    )


def _render_table(block: str) -> str:
    c = _md_colors()
    lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return _render_paragraph(block)

    def parse_row(line: str) -> list[str]:
        cells = line.split("|")
        if cells and cells[0].strip() == "":
            cells = cells[1:]
        if cells and cells[-1].strip() == "":
            cells = cells[:-1]
        return [c.strip() for c in cells]

    header_cells = parse_row(lines[0])
    separator_idx = 1
    data_lines = lines[separator_idx + 1:] if separator_idx < len(lines) else []

    rows_html = ""
    th_cells = "".join(
        f'<th style="padding:8px 12px; text-align:left; font-weight:600; color:{c["text"]}; '
        f'background-color:{c["card_alt"]}; border-bottom:2px solid {c["blue"]}; font-size:12px;">'
        f'{_inline_format(html.escape(cell))}</th>'
        for cell in header_cells
    )
    rows_html += f"<tr>{th_cells}</tr>\n"

    for i, line in enumerate(data_lines):
        cells = parse_row(line)
        bg = c["card"] if i % 2 == 0 else c["toolbar"]
        td_cells = "".join(
            f'<td style="padding:6px 12px; border-bottom:1px solid {c["border"]}; color:{c["body"]}; '
            f'font-size:13px; line-height:1.5; background-color:{bg};">{_inline_format(html.escape(cell))}</td>'
            for cell in cells
        )
        rows_html += f"<tr>{td_cells}</tr>\n"

    return (
        f'<table style="border-collapse:collapse; width:100%; margin:8px 0; '
        f'border:1px solid {c["border"]}; border-radius:10px; overflow:hidden;">'
        f'{rows_html}</table>'
    )


def _render_unordered_list(block: str) -> str:
    c = _md_colors()
    items: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "+ ")):
            items.append(stripped[2:].strip())
        elif items:
            items[-1] += " " + stripped
    li_html = "".join(
        f'<li style="margin:5px 0; color:{c["text"]}; font-size:14px; line-height:1.7;">{_inline_format(html.escape(item))}</li>'
        for item in items
    )
    return f'<ul style="margin:6px 0; padding-left:24px;">{li_html}</ul>'


def _render_ordered_list(block: str) -> str:
    c = _md_colors()
    items: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        match = re.match(r"^\d+\.\s+(.*)", stripped)
        if match:
            items.append(match.group(1))
        elif items:
            items[-1] += " " + stripped
    li_html = "".join(
        f'<li style="margin:5px 0; color:{c["text"]}; font-size:14px; line-height:1.7;">{_inline_format(html.escape(item))}</li>'
        for item in items
    )
    return f'<ol style="margin:6px 0; padding-left:24px;">{li_html}</ol>'


def _render_blockquote(block: str) -> str:
    c = _md_colors()
    lines = [l.lstrip("> ").strip() for l in block.split("\n")]
    content = "<br/>".join(_inline_format(html.escape(l)) for l in lines)
    return (
        f'<div style="border-left:3px solid {c["blue"]}; padding:10px 16px; margin:8px 0; '
        f'background-color:{c["toolbar"]}; color:{c["muted"]}; font-size:14px; line-height:1.6; '
        f'border-radius:0 12px 12px 0;">'
        f'{content}</div>'
    )


def _render_paragraph(block: str) -> str:
    c = _md_colors()
    text = block.replace("\n", "<br/>")
    text = _inline_format(html.escape(text).replace("&lt;br/&gt;", "<br/>"))
    return f'<p style="margin:7px 0; line-height:1.76; color:{c["text"]}; font-size:14px; letter-spacing:0;">{text}</p>'


def _inline_format(text: str) -> str:
    """Apply inline markdown formatting (bold, italic, code, links, file paths)."""
    c = _md_colors()
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.+?)\*\*', rf'<b style="color:{c["text"]};">\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`\n]+?)`',
                  rf'<code style="background-color:{c["card_alt"]}; color:{c["warning"]}; padding:2px 6px; '
                  rf'border-radius:6px; font-family:Cascadia Mono,Consolas,monospace; font-size:12px;">\1</code>',
                  text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  rf'<a href="\2" style="color:{c["blue"]}; text-decoration:none;">\1</a>',
                  text)
    text = _linkify_file_paths(text)
    return text


def _linkify_file_paths(text: str) -> str:
    """Convert Windows file paths (D:\\...\\file.ext) to clickable links."""
    def _replace_path(m: re.Match) -> str:
        path = m.group(0)
        if f'href="{path}"' in text or f">{path}<" in text:
            return path
        display = path
        if len(display) > 60:
            parts = path.replace("\\", "/").split("/")
            display = parts[0] + "/.../" + parts[-1]
        return (
            f'<a href="{path}" style="color:{_md_colors()["warning"]}; text-decoration:underline; '
            f'cursor:pointer;" title="点击打开文件">{html.escape(display)}</a>'
        )

    return re.sub(
        r'[A-Z]:\\[^\s<>"\',:;\)\]]+\.\w{1,5}',
        _replace_path,
        text,
    )


_CSS_STYLE = ""
