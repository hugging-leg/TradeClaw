"""
Tests for LLM Configuration System

Tests the flexible LLM configuration including:
- LLMConfigManager loading, saving, migration
- Provider/model resolution
- Role bindings
- Singleton behavior
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_trader.config.llm_config import (
    LLMModelConfig,
    LLMProviderConfig,
    LLMRolesConfig,
    LLMConfigFile,
    LLMConfigManager,
    get_llm_config_manager,
)


class TestLLMModels:
    """Test Pydantic models"""

    def test_model_config(self):
        m = LLMModelConfig(id="gpt4o", model_id="gpt-4o")
        assert m.id == "gpt4o"
        assert m.model_id == "gpt-4o"
        assert m.temperature == 0.1

    def test_provider_config(self):
        p = LLMProviderConfig(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            models=[
                LLMModelConfig(id="gpt4o", model_id="gpt-4o"),
            ],
        )
        assert p.id == "openai"
        assert len(p.models) == 1

    def test_roles_config_defaults(self):
        r = LLMRolesConfig()
        assert r.agent == "default"
        assert r.news_filter == "default"
        assert r.memory_summary == "default"

    def test_roles_config_extra_fields(self):
        r = LLMRolesConfig(agent="gpt4o", custom_role="deepseek-chat")
        assert r.agent == "gpt4o"
        assert r.custom_role == "deepseek-chat"

    def test_config_file(self):
        cf = LLMConfigFile()
        assert cf.providers == []
        assert cf.roles.agent == "default"


class TestLLMConfigManager:
    """Test LLMConfigManager"""

    @pytest.fixture
    def tmp_data_dir(self, tmp_path):
        return str(tmp_path)

    @pytest.fixture
    def sample_config(self):
        return LLMConfigFile(
            providers=[
                LLMProviderConfig(
                    id="openai",
                    name="OpenAI",
                    base_url="https://api.openai.com/v1",
                    api_key="sk-test-key",
                    models=[
                        LLMModelConfig(id="gpt4o", name="GPT-4o", model_id="gpt-4o", temperature=0.1),
                        LLMModelConfig(id="gpt4o-mini", name="GPT-4o Mini", model_id="gpt-4o-mini", temperature=0.3),
                    ],
                ),
                LLMProviderConfig(
                    id="deepseek",
                    name="DeepSeek",
                    base_url="https://api.deepseek.com/v1",
                    api_key="ds-test-key",
                    models=[
                        LLMModelConfig(id="ds-chat", name="DeepSeek Chat", model_id="deepseek-chat", temperature=0.1),
                    ],
                ),
            ],
            roles=LLMRolesConfig(agent="gpt4o", news_filter="ds-chat", memory_summary="gpt4o-mini"),
        )

    @pytest.fixture
    def manager_with_config(self, tmp_data_dir, sample_config):
        """Create a manager with pre-existing config file"""
        config_path = Path(tmp_data_dir) / "llm_config.yaml"
        data = sample_config.model_dump()
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return LLMConfigManager(data_dir=tmp_data_dir)

    def test_load_existing_config(self, manager_with_config):
        """Test loading from existing YAML"""
        config = manager_with_config.get_config()
        assert len(config.providers) == 2
        assert config.providers[0].id == "openai"
        assert len(config.providers[0].models) == 2

    def test_resolve_model(self, manager_with_config):
        """Test resolving a model by id"""
        result = manager_with_config.resolve_model("gpt4o")
        assert result is not None
        base_url, api_key, model_id, temp = result
        assert base_url == "https://api.openai.com/v1"
        assert api_key == "sk-test-key"
        assert model_id == "gpt-4o"
        assert temp == 0.1

    def test_resolve_model_different_provider(self, manager_with_config):
        """Test resolving a model from a different provider"""
        result = manager_with_config.resolve_model("ds-chat")
        assert result is not None
        base_url, api_key, model_id, temp = result
        assert base_url == "https://api.deepseek.com/v1"
        assert api_key == "ds-test-key"
        assert model_id == "deepseek-chat"

    def test_resolve_model_not_found(self, manager_with_config):
        """Test resolving a non-existent model"""
        result = manager_with_config.resolve_model("nonexistent")
        assert result is None

    def test_resolve_role(self, manager_with_config):
        """Test resolving a role to model config"""
        result = manager_with_config.resolve_role("agent")
        assert result is not None
        base_url, api_key, model_id, temp = result
        assert model_id == "gpt-4o"

    def test_resolve_role_news_filter(self, manager_with_config):
        """Test resolving news_filter role"""
        result = manager_with_config.resolve_role("news_filter")
        assert result is not None
        _, _, model_id, _ = result
        assert model_id == "deepseek-chat"

    def test_resolve_role_not_found(self, manager_with_config):
        """Test resolving a non-existent role"""
        result = manager_with_config.resolve_role("nonexistent_role")
        assert result is None

    def test_get_all_model_names(self, manager_with_config):
        """Test getting all model names"""
        models = manager_with_config.get_all_model_names()
        assert len(models) == 3
        ids = {m["id"] for m in models}
        assert "gpt4o" in ids
        assert "gpt4o-mini" in ids
        assert "ds-chat" in ids

    def test_get_providers_sanitized(self, manager_with_config):
        """Test that API keys are masked"""
        providers = manager_with_config.get_providers_sanitized()
        assert len(providers) == 2
        for p in providers:
            key = p["api_key"]
            assert "*" in key  # Key should be masked

    def test_get_roles(self, manager_with_config):
        """Test getting role bindings"""
        roles = manager_with_config.get_roles()
        assert roles["agent"] == "gpt4o"
        assert roles["news_filter"] == "ds-chat"
        assert roles["memory_summary"] == "gpt4o-mini"

    def test_update_roles(self, manager_with_config):
        """Test updating role bindings"""
        updated = manager_with_config.update_roles({"agent": "ds-chat"})
        assert updated["agent"] == "ds-chat"
        # Verify persistence
        roles = manager_with_config.get_roles()
        assert roles["agent"] == "ds-chat"

    def test_save_and_reload(self, tmp_data_dir, sample_config):
        """Test save + reload roundtrip"""
        manager = LLMConfigManager(data_dir=tmp_data_dir)
        manager.save_config(sample_config)

        manager2 = LLMConfigManager(data_dir=tmp_data_dir)
        config = manager2.get_config()
        assert len(config.providers) == 2
        assert config.roles.agent == "gpt4o"

    def test_update_config(self, manager_with_config):
        """Test updating config via dict"""
        new_data = {
            "providers": [
                {
                    "id": "only-provider",
                    "name": "Only",
                    "base_url": "http://only.com",
                    "api_key": "only-key",
                    "models": [{"id": "m1", "model_id": "model-1"}],
                }
            ],
            "roles": {"agent": "m1", "news_filter": "m1", "memory_summary": "m1"},
        }
        config = manager_with_config.update_config(new_data)
        assert len(config.providers) == 1
        assert config.providers[0].id == "only-provider"

    def test_migration_creates_empty_when_no_key(self, tmp_data_dir):
        """Test migration with no API key creates empty config"""
        mock_settings = MagicMock()
        mock_settings.data_dir = tmp_data_dir
        mock_settings.llm_base_url = "https://api.openai.com/v1"
        mock_settings.llm_api_key = ""
        mock_settings.llm_model = "gpt-4o"
        with patch("config.settings", mock_settings):
            manager = LLMConfigManager(data_dir=tmp_data_dir)
            config = manager.get_config()
            assert len(config.providers) == 0

    def test_reload(self, manager_with_config, tmp_data_dir):
        """Test force reload"""
        # Modify the file directly
        config_path = Path(tmp_data_dir) / "llm_config.yaml"
        new_config = LLMConfigFile(
            providers=[
                LLMProviderConfig(
                    id="new",
                    name="New",
                    base_url="http://new.com",
                    api_key="new-key",
                    models=[LLMModelConfig(id="new-m", model_id="new-model")],
                )
            ],
        )
        with open(config_path, "w") as f:
            yaml.dump(new_config.model_dump(), f)

        reloaded = manager_with_config.reload()
        assert len(reloaded.providers) == 1
        assert reloaded.providers[0].id == "new"


class TestLLMConfigManagerSingleton:
    """Test singleton behavior"""

    def test_singleton(self, tmp_path):
        """Test get_llm_config_manager returns same instance"""
        import agent_trader.config.llm_config as llm_mod
        # Reset singleton
        llm_mod._manager = None
        mock_settings = MagicMock()
        mock_settings.data_dir = str(tmp_path)
        mock_settings.llm_base_url = "https://api.openai.com/v1"
        mock_settings.llm_api_key = ""
        mock_settings.llm_model = "gpt-4o"
        with patch("config.settings", mock_settings):
            m1 = get_llm_config_manager()
            m2 = get_llm_config_manager()
            assert m1 is m2
            # Cleanup
            llm_mod._manager = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
