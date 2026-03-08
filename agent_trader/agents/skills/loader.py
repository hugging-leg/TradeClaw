"""
Skills Loader — 扫描 agent_trader/skills/*.md，解析 YAML frontmatter，
生成系统提示词中的 <available_skills> 摘要，并提供 read_skill tool。

设计参考 OpenClaw 的 Skills 系统：
- 每个 skill 是一个 .md 文件，包含 YAML frontmatter (name, description) + markdown 正文
- 系统提示词只注入 name + description 摘要（节省 token）
- Agent 通过 read_skill tool 按需读取完整内容
- 新增 skill 只需放入 agent_trader/skills/ 目录，无需改代码
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)

# Skills 目录（agent_trader/skills/）
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


@dataclass
class SkillEntry:
    """解析后的 skill 条目"""
    name: str
    description: str
    file_path: Path
    body: str  # markdown 正文（不含 frontmatter）


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_skill_file(path: Path) -> Optional[SkillEntry]:
    """解析单个 skill .md 文件"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("无法读取 skill 文件 %s: %s", path, e)
        return None

    match = _FRONTMATTER_RE.match(text)
    if not match:
        logger.warning("Skill 文件 %s 缺少 YAML frontmatter，跳过", path.name)
        return None

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        logger.warning("Skill 文件 %s frontmatter 解析失败: %s", path.name, e)
        return None

    if not isinstance(meta, dict):
        logger.warning("Skill 文件 %s frontmatter 不是 dict，跳过", path.name)
        return None

    name = meta.get("name", path.stem)
    description = meta.get("description", "")

    body = text[match.end():]

    return SkillEntry(
        name=name,
        description=description,
        file_path=path,
        body=body.strip(),
    )


class SkillLoader:
    """
    Skills 加载器

    用法：
        loader = SkillLoader()
        prompt = loader.build_skills_prompt()  # 注入到系统提示词
        tool = loader.create_read_skill_tool()  # 注册为 agent tool
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self._dir = skills_dir or _SKILLS_DIR
        self._skills: Dict[str, SkillEntry] = {}
        self._load()

    def _load(self) -> None:
        """扫描并加载所有 skill 文件"""
        if not self._dir.exists():
            logger.info("Skills 目录不存在: %s", self._dir)
            return

        for path in sorted(self._dir.glob("*.md")):
            entry = _parse_skill_file(path)
            if entry:
                self._skills[entry.name] = entry
                logger.debug("Loaded skill: %s (%s)", entry.name, entry.description[:60])

        logger.info("已加载 %d 个 skills", len(self._skills))

    @property
    def skills(self) -> Dict[str, SkillEntry]:
        return self._skills

    def get_skill(self, name: str) -> Optional[SkillEntry]:
        return self._skills.get(name)

    def build_skills_prompt(self) -> str:
        """
        生成 <available_skills> 提示词片段，注入到系统提示词中。

        格式：
            ## Skills
            Before acting, scan <available_skills> descriptions.
            If a skill applies, use `read_skill` tool to load its full guide, then follow it.

            <available_skills>
            - scheduling: 自主调度（at/every/cron）使用指南
            - subagent: 子Agent并行分析使用指南
            ...
            </available_skills>
        """
        if not self._skills:
            return ""

        lines = [
            "## Skills",
            "Before acting on a task, scan <available_skills> descriptions below.",
            "If a skill clearly applies, use `read_skill` tool to load its full guide, then follow it.",
            "If none apply, proceed normally without reading any skill.",
            "",
            "<available_skills>",
        ]

        for entry in self._skills.values():
            lines.append(f"- {entry.name}: {entry.description}")

        lines.append("</available_skills>")
        lines.append("")

        return "\n".join(lines)

    def create_read_skill_tool(self):
        """
        创建 read_skill LangChain tool。

        Agent 调用此 tool 按名称读取 skill 的完整内容。
        """
        from langchain.tools import tool

        skills_ref = self._skills

        @tool
        def read_skill(skill_name: str) -> str:
            """
            读取指定 skill 的完整使用指南。

            在执行特定类型的任务前，先用此工具读取对应 skill 的详细说明，
            了解可用工具、最佳实践和使用模式。

            Args:
                skill_name: skill 名称（从 <available_skills> 列表中选择）

            Returns:
                skill 的完整 markdown 内容，包含详细说明和示例
            """
            entry = skills_ref.get(skill_name)
            if not entry:
                available = ", ".join(skills_ref.keys()) if skills_ref else "(none)"
                return f"未找到 skill '{skill_name}'。可用 skills: {available}"
            return entry.body

        return read_skill
