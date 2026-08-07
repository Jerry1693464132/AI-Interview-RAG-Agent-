"""Prompt 模板管理 — 轻量级加载器，按需扩展。"""

import re


def clean_json_response(raw: str) -> str:
    """清理 LLM 返回的 markdown 代码块标记（多个服务共用）。"""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text
