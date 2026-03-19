from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from shap_llm_builder import build_combined_llm_payload

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = BASE_DIR / "prompts"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def load_prompt(filename: str) -> str:
    path = PROMPT_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def generate_combined_interpretation(
    short_result: Dict[str, Any],
    long_result: Dict[str, Any],
) -> Dict[str, Any]:
    system_prompt = load_prompt("system_prompt.txt")
    user_template = load_prompt("user_prompt.txt")

    payload = build_combined_llm_payload(
        short_result=short_result,
        long_result=long_result,
    )

    user_prompt = user_template.format(**payload)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM 응답이 비어 있습니다.")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(f"LLM JSON 파싱 실패: {content}")
    
