from utils.text_utils import compact_text


def summarize_text(text: str) -> str:
    return compact_text(text, 500)
