from __future__ import annotations

import html
import re


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
    line = block.split("\n")[0]
    level = 0
    for ch in line:
        if ch == "#":
            level += 1
        else:
            break
    level = min(level, 6)
    text = _inline_format(html.escape(line.lstrip("# ").strip()))
    sizes = {1: "20px", 2: "17px", 3: "15px", 4: "14px", 5: "13px", 6: "13px"}
    weights = {1: "700", 2: "700", 3: "600", 4: "600", 5: "600", 6: "500"}
    size = sizes.get(level, "14px")
    weight = weights.get(level, "600")
    color = "#F0F2F5" if level <= 2 else "#D1D5DB"
    margin = "16px 0 8px 0" if level <= 2 else "12px 0 6px 0"
    border = "border-bottom: 1px solid #252A35; padding-bottom: 6px;" if level <= 2 else ""
    return f'<div style="font-size:{size}; font-weight:{weight}; color:{color}; margin:{margin}; {border}">{text}</div>'


def _render_code_block(block: str) -> str:
    lines = block.split("\n")
    lang = lines[0].strip().lstrip("`").strip() if lines else ""
    code_lines = lines[1:-1] if len(lines) > 2 and lines[-1].strip().startswith("```") else lines[1:]
    code = html.escape("\n".join(code_lines))
    lang_badge = f'<span style="color:#6B7280; font-size:11px; float:right;">{html.escape(lang)}</span>' if lang else ""
    return (
        f'<div style="background-color:#0D1017; border:1px solid #252A35; border-radius:8px; '
        f'padding:12px 14px; margin:8px 0; font-family:Cascadia Mono,Consolas,monospace; '
        f'font-size:12px; color:#D1D5DB; white-space:pre-wrap; overflow-x:auto;">'
        f'{lang_badge}<code>{code}</code></div>'
    )


def _render_table(block: str) -> str:
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
        f'<th style="padding:8px 12px; text-align:left; font-weight:600; color:#F0F2F5; '
        f'background-color:#1C2029; border-bottom:2px solid #3B82F6; font-size:12px;">'
        f'{_inline_format(html.escape(c))}</th>'
        for c in header_cells
    )
    rows_html += f"<tr>{th_cells}</tr>\n"

    for i, line in enumerate(data_lines):
        cells = parse_row(line)
        bg = "#161921" if i % 2 == 0 else "#111318"
        td_cells = "".join(
            f'<td style="padding:6px 12px; border-bottom:1px solid #252A35; color:#D1D5DB; '
            f'font-size:12px; background-color:{bg};">{_inline_format(html.escape(c))}</td>'
            for c in cells
        )
        rows_html += f"<tr>{td_cells}</tr>\n"

    return (
        f'<table style="border-collapse:collapse; width:100%; margin:8px 0; '
        f'border:1px solid #252A35; border-radius:6px; overflow:hidden;">'
        f'{rows_html}</table>'
    )


def _render_unordered_list(block: str) -> str:
    items: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "+ ")):
            items.append(stripped[2:].strip())
        elif items:
            items[-1] += " " + stripped
    li_html = "".join(
        f'<li style="margin:3px 0; color:#D1D5DB; font-size:13px;">{_inline_format(html.escape(item))}</li>'
        for item in items
    )
    return f'<ul style="margin:6px 0; padding-left:24px;">{li_html}</ul>'


def _render_ordered_list(block: str) -> str:
    items: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        match = re.match(r"^\d+\.\s+(.*)", stripped)
        if match:
            items.append(match.group(1))
        elif items:
            items[-1] += " " + stripped
    li_html = "".join(
        f'<li style="margin:3px 0; color:#D1D5DB; font-size:13px;">{_inline_format(html.escape(item))}</li>'
        for item in items
    )
    return f'<ol style="margin:6px 0; padding-left:24px;">{li_html}</ol>'


def _render_blockquote(block: str) -> str:
    lines = [l.lstrip("> ").strip() for l in block.split("\n")]
    content = "<br/>".join(_inline_format(html.escape(l)) for l in lines)
    return (
        f'<div style="border-left:3px solid #3B82F6; padding:8px 14px; margin:8px 0; '
        f'background-color:#111318; color:#9CA3AF; font-size:13px; border-radius:0 6px 6px 0;">'
        f'{content}</div>'
    )


def _render_paragraph(block: str) -> str:
    text = block.replace("\n", "<br/>")
    text = _inline_format(html.escape(text).replace("&lt;br/&gt;", "<br/>"))
    return f'<p style="margin:6px 0; line-height:1.7; color:#D1D5DB; font-size:13px;">{text}</p>'


def _inline_format(text: str) -> str:
    """Apply inline markdown formatting (bold, italic, code, links, file paths)."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b style="color:#F0F2F5;">\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`\n]+?)`',
                  r'<code style="background-color:#1C2029; color:#F59E0B; padding:1px 5px; '
                  r'border-radius:3px; font-family:Cascadia Mono,Consolas,monospace; font-size:12px;">\1</code>',
                  text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  r'<a href="\2" style="color:#3B82F6; text-decoration:none;">\1</a>',
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
            f'<a href="{path}" style="color:#F59E0B; text-decoration:underline; '
            f'cursor:pointer;" title="点击打开文件">{html.escape(display)}</a>'
        )

    return re.sub(
        r'[A-Z]:\\[^\s<>"\',:;\)\]]+\.\w{1,5}',
        _replace_path,
        text,
    )


_CSS_STYLE = ""
