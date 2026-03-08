"""
Tests for the Skills system — loader, prompt generation, and read_skill tool.
"""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSkillLoader:
    """Tests for SkillLoader class."""

    def _make_skill_file(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper to create a skill markdown file."""
        path = tmp_path / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_load_valid_skill(self, tmp_path):
        """Load a valid skill file with YAML frontmatter."""
        self._make_skill_file(tmp_path, "test_skill", textwrap.dedent("""\
            ---
            name: test_skill
            description: A test skill for unit testing
            ---

            # Test Skill

            This is the body of the test skill.
            It contains instructions for the agent.
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert len(loader.skills) == 1
        assert "test_skill" in loader.skills

        entry = loader.skills["test_skill"]
        assert entry.name == "test_skill"
        assert entry.description == "A test skill for unit testing"
        assert "# Test Skill" in entry.body
        assert "instructions for the agent" in entry.body

    def test_load_multiple_skills(self, tmp_path):
        """Load multiple skill files."""
        self._make_skill_file(tmp_path, "alpha", textwrap.dedent("""\
            ---
            name: alpha
            description: Alpha skill
            ---
            Alpha body
        """))
        self._make_skill_file(tmp_path, "beta", textwrap.dedent("""\
            ---
            name: beta
            description: Beta skill
            ---
            Beta body
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert len(loader.skills) == 2
        assert "alpha" in loader.skills
        assert "beta" in loader.skills

    def test_skip_file_without_frontmatter(self, tmp_path):
        """Files without YAML frontmatter are skipped."""
        self._make_skill_file(tmp_path, "no_frontmatter", "# Just a markdown file\nNo frontmatter here.")

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert len(loader.skills) == 0

    def test_skip_invalid_yaml(self, tmp_path):
        """Files with invalid YAML frontmatter are skipped."""
        self._make_skill_file(tmp_path, "bad_yaml", textwrap.dedent("""\
            ---
            name: [invalid yaml
            ---
            Body
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert len(loader.skills) == 0

    def test_empty_directory(self, tmp_path):
        """Empty directory returns no skills."""
        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert len(loader.skills) == 0

    def test_nonexistent_directory(self, tmp_path):
        """Nonexistent directory returns no skills."""
        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path / "nonexistent")
        assert len(loader.skills) == 0

    def test_build_skills_prompt_empty(self, tmp_path):
        """Empty skills dir produces empty prompt."""
        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert loader.build_skills_prompt() == ""

    def test_build_skills_prompt_content(self, tmp_path):
        """Skills prompt contains skill names and descriptions."""
        self._make_skill_file(tmp_path, "scheduling", textwrap.dedent("""\
            ---
            name: scheduling
            description: Schedule analysis tasks
            ---
            Scheduling guide body
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        prompt = loader.build_skills_prompt()
        assert "<available_skills>" in prompt
        assert "</available_skills>" in prompt
        assert "scheduling: Schedule analysis tasks" in prompt
        assert "read_skill" in prompt

    def test_get_skill(self, tmp_path):
        """get_skill returns the correct entry or None."""
        self._make_skill_file(tmp_path, "test", textwrap.dedent("""\
            ---
            name: test
            description: Test
            ---
            Body
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        assert loader.get_skill("test") is not None
        assert loader.get_skill("nonexistent") is None

    def test_read_skill_tool(self, tmp_path):
        """read_skill tool returns correct content."""
        self._make_skill_file(tmp_path, "test_skill", textwrap.dedent("""\
            ---
            name: test_skill
            description: A test skill
            ---

            # Detailed Guide

            Step 1: Do this
            Step 2: Do that
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        tool = loader.create_read_skill_tool()

        # Invoke the tool
        result = tool.invoke({"skill_name": "test_skill"})
        assert "# Detailed Guide" in result
        assert "Step 1: Do this" in result

    def test_read_skill_tool_not_found(self, tmp_path):
        """read_skill tool returns error for unknown skill."""
        self._make_skill_file(tmp_path, "existing", textwrap.dedent("""\
            ---
            name: existing
            description: Exists
            ---
            Body
        """))

        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader(skills_dir=tmp_path)
        tool = loader.create_read_skill_tool()

        result = tool.invoke({"skill_name": "nonexistent"})
        assert "未找到" in result
        assert "existing" in result  # Should list available skills


class TestProductionSkillFiles:
    """Verify that the production skill files in agent_trader/skills/ are valid."""

    def test_production_skills_load(self):
        """All production skill files should load without errors."""
        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader()  # Uses default _SKILLS_DIR
        # We expect at least the 6 skill files we created
        assert len(loader.skills) >= 6, (
            f"Expected at least 6 skills, got {len(loader.skills)}: "
            f"{list(loader.skills.keys())}"
        )

    def test_production_skills_have_descriptions(self):
        """All production skills should have non-empty descriptions."""
        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader()
        for name, entry in loader.skills.items():
            assert entry.description, f"Skill '{name}' has empty description"
            assert entry.body, f"Skill '{name}' has empty body"

    def test_production_skills_prompt(self):
        """The built prompt should mention all skills."""
        from agent_trader.agents.skills.loader import SkillLoader

        loader = SkillLoader()
        prompt = loader.build_skills_prompt()
        for name in loader.skills:
            assert name in prompt, f"Skill '{name}' not in prompt"
