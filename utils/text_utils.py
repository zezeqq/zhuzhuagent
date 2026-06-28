import re


def compact_text(text: str, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def keywords_from_query(text: str) -> list[str]:
    parts = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    return [p for p in parts if len(p) > 1][:12]
