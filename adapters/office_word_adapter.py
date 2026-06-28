from __future__ import annotations

from pathlib import Path

from docx import Document

from artifacts.artifact_manager import ensure_export_dir


def create_word_document(title: str, sections: list[tuple[str, str]], output_name: str) -> Path:
    out_dir = ensure_export_dir()
    path = out_dir / output_name
    document = Document()
    document.add_heading(title, level=0)
    for heading, body in sections:
        document.add_heading(heading, level=1)
        for paragraph in body.splitlines():
            paragraph = paragraph.strip()
            if paragraph:
                document.add_paragraph(paragraph)
    document.save(path)
    return path
