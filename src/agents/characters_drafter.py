"""CharactersDrafter — turn a free-text character brief into characters.yaml.

Single LLM call. Returns dict with schema:
  {
    "protagonist": {"name": str, "description": str, "arc": str (optional)},
    "supporting": [
      {"name": str, "role": str, "description": str},
      ...
    ]
  }

The protagonist.name is overridden with what the user typed in step 1
of the wizard when provided (authoritative source). If the user left it
blank, the LLM-suggested name is kept instead (fallback: "主角").
"""
from __future__ import annotations

import logging

import yaml

from src import llm

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是资深中文小说责编。用户给你一段自由文本描述主要人物，请输出严格的 YAML 人物档案。

YAML schema（必须严格遵守）：
protagonist:
  name: "<主角姓名>"
  description: "<两三句人物小传>"
  arc: "<(可选) 人物弧光一句话>"
supporting:
  - name: "<配角 1>"
    role: "<在故事中的功能, 如小弟/情敌/情报线>"
    description: "<两三句>"
  - name: "..."
    role: "..."
    description: "..."

规则：
1. 只输出 YAML，不要 markdown 代码块，不要额外注释。
2. supporting 至少 2 个、最多 8 个。
3. 若简介信息不足，合理扩展。
"""


class CharactersDrafter:
    def run(self, *, brief: str, protagonist_name: str) -> dict:
        shell = {
            "protagonist": {"name": protagonist_name or "主角", "description": ""},
            "supporting": [],
        }
        if not brief or not brief.strip():
            return shell

        if protagonist_name:
            user = f"主角姓名（请在 protagonist.name 沿用此名）：{protagonist_name}\n\n人物简介：\n{brief}\n"
        else:
            user = (
                "主角姓名未指定，请你在 protagonist.name 起一个符合故事基调的中文姓名。\n\n"
                f"人物简介：\n{brief}\n"
            )
        try:
            raw = llm.chat(
                system=SYSTEM_PROMPT,
                user=user,
                agent_name="characters_drafter",
                temperature=0.4,
                response_format="text",
            ) or ""
            if raw.startswith("```"):
                raw = raw.strip("`").partition("\n")[2].rpartition("```")[0]
            data = yaml.safe_load(raw)
        except (yaml.YAMLError, KeyError) as exc:
            log.warning("CharactersDrafter bad YAML, returning shell: %s", exc)
            return shell

        if not isinstance(data, dict):
            return shell
        proto = data.get("protagonist") or {}
        # user-typed name wins — but only if the user actually typed one.
        # When protagonist_name is empty, keep the LLM-suggested name.
        if protagonist_name:
            proto["name"] = protagonist_name
        elif not proto.get("name"):
            proto["name"] = "主角"
        supp = data.get("supporting") or []
        if not isinstance(supp, list):
            supp = []
        return {"protagonist": proto, "supporting": supp}
