from __future__ import annotations

import json
from pathlib import Path


from utils.path_utils import resource_path

CONFIG_PATH = resource_path("config", "prompt_templates.json")


def load_prompts() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


from core.app_identity import APP_NAME


def get_system_prompt() -> str:
    prompts = load_prompts()
    return prompts.get("agent_system_prompt", f"你是 {APP_NAME}，是用户的本地工程技术工作智能体。")
