def build_citations(chunks):
    lines = []
    for idx, c in enumerate(chunks, 1):
        source = c.get("file_name") or c.get("standard_code") or f"文件ID {c.get('file_id')}"
        page = c.get("page_number") or "-"
        lines.append(f"[{idx}] {source}，页码：{page}")
    return "\n".join(lines)
