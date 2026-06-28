from pathlib import Path
from rag.document_loader import load_text


def read_file(path: str) -> str:
    pages = load_text(Path(path))
    return "\n".join(page["text"] for page in pages)
