"""
LLM Configuration Manager

Manages read/write, caching, and backward-compatible migration for
user_data/llm_config.yaml.

Data models:
- LLMProviderConfig: An API provider (base_url + api_key + models[])
- LLMModelConfig: A model under a provider (id + model_id + temperature)
- LLMRolesConfig: Role bindings (functional module -> model id)
- LLMConfigFile: Complete YAML file structure

Usage:
    mgr = get_llm_config_manager()
    cfg = mgr.get_config()
    resolved = mgr.resolve_model("gpt4o")  # -> (base_url, api_key, model_id, temperature)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================
# Pydantic Models
# ============================================================

class LLMModelConfig(BaseModel):
    """An available LLM model."""
    id: str = Field(..., description="Globally unique identifier, used for role binding and agent config references")
    name: str = Field("", description="Human-readable display name")
    model_id: str = Field(..., description="Actual model field value passed to the API")
    temperature: float = Field(0.1, ge=0.0, le=2.0)


class LLMProviderConfig(BaseModel):
    """An API Provider."""
    id: str = Field(..., description="Provider unique identifier")
    name: str = Field("", description="Human-readable display name")
    base_url: str = Field(..., description="API base URL")
    api_key: str = Field("", description="API Key")
    models: List[LLMModelConfig] = Field(default_factory=list)


class LLMRolesConfig(BaseModel):
    """Role bindings: functional module -> model id."""
    model_config = {"extra": "allow"}  # Allow user-defined custom roles

    agent: str = Field("default", description="Default model for agent workflow")
    news_filter: str = Field("default", description="Model for news filtering")
    memory_summary: str = Field("default", description="Model for memory summarization")


class LLMConfigFile(BaseModel):
    """Complete LLM configuration file."""
    providers: List[LLMProviderConfig] = Field(default_factory=list)
    roles: LLMRolesConfig = Field(default_factory=LLMRolesConfig)


# ============================================================
# Config Manager
# ============================================================

class LLMConfigManager:
    """
    LLM Configuration Manager (singleton)

    - Reads/writes user_data/llm_config.yaml
    - Auto-migrates from .env on first startup
    - Provides resolve_model(name) to resolve model -> (base_url, api_key, model_id, temperature)
    - Thread-safe caching
    """

    def __init__(self, data_dir: str = "./user_data"):
        self._data_dir = Path(data_dir)
        self._config_path = self._data_dir / "llm_config.yaml"
        self._config: Optional[LLMConfigFile] = None
        self._lock = threading.Lock()

        # Ensure directory exists
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Load or migrate
        self._load_or_migrate()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self) -> LLMConfigFile:
        """Get current configuration (cached)."""
        with self._lock:
            if self._config is None:
                self._load_or_migrate()
            return self._config  # type: ignore

    def save_config(self, config: LLMConfigFile) -> None:
        """Save configuration to YAML file."""
        with self._lock:
            self._config = config
            self._write_yaml(config)

    def update_config(self, data: Dict[str, Any]) -> LLMConfigFile:
        """Update configuration from dict (used by API PUT)."""
        config = LLMConfigFile(**data)
        self.save_config(config)
        return config

    def get_providers_sanitized(self) -> List[Dict[str, Any]]:
        """Get provider list with api_key masked."""
        config = self.get_config()
        result = []
        for provider in config.providers:
            p = provider.model_dump()
            key = p.get("api_key", "")
            if len(key) > 8:
                p["api_key"] = f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"
            elif key:
                p["api_key"] = "*" * len(key)
            result.append(p)
        return result

    def get_all_model_names(self) -> List[Dict[str, str]]:
        """Get all registered models (id + name + provider_name)."""
        config = self.get_config()
        result = []
        for provider in config.providers:
            for model in provider.models:
                result.append({
                    "id": model.id,
                    "name": model.name or model.id,
                    "provider_id": provider.id,
                    "provider_name": provider.name or provider.id,
                    "model_id": model.model_id,
                })
        return result

    def resolve_model(self, model_name: str) -> Optional[Tuple[str, str, str, float]]:
        """
        Resolve model name -> (base_url, api_key, model_id, temperature).

        Returns None if model_name is not found.
        """
        config = self.get_config()
        for provider in config.providers:
            for model in provider.models:
                if model.id == model_name:
                    return (
                        provider.base_url,
                        provider.api_key,
                        model.model_id,
                        model.temperature,
                    )
        return None

    def resolve_role(self, role: str) -> Optional[Tuple[str, str, str, float]]:
        """
        Resolve role -> (base_url, api_key, model_id, temperature).

        Looks up the model name from roles first, then resolves the model.
        """
        config = self.get_config()
        roles_dict = config.roles.model_dump()
        model_name = roles_dict.get(role)
        if not model_name:
            return None
        return self.resolve_model(model_name)

    def get_roles(self) -> Dict[str, str]:
        """Get role bindings (role_name -> model_id)."""
        return self.get_config().roles.model_dump()

    def update_roles(self, updates: Dict[str, str]) -> Dict[str, str]:
        """Update role bindings."""
        config = self.get_config()
        current = config.roles.model_dump()
        current.update(updates)
        config.roles = LLMRolesConfig(**current)
        self.save_config(config)
        return config.roles.model_dump()

    def reload(self) -> LLMConfigFile:
        """Force reload from file."""
        with self._lock:
            self._config = None
            self._load_or_migrate()
            return self._config  # type: ignore

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_or_migrate(self) -> None:
        """Load YAML or migrate from .env."""
        if self._config_path.exists():
            self._load_yaml()
        else:
            self._migrate_from_env()

    def _load_yaml(self) -> None:
        """Load from YAML file."""
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._config = LLMConfigFile(**raw)
            logger.info(
                "LLM config loaded: %d providers, %d total models",
                len(self._config.providers),
                sum(len(p.models) for p in self._config.providers),
            )
        except Exception as e:
            logger.error("Failed to load LLM config from %s: %s", self._config_path, e)
            self._config = LLMConfigFile()

    def _write_yaml(self, config: LLMConfigFile) -> None:
        """Write to YAML file."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = config.model_dump()
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data, f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        logger.info("LLM config saved to %s", self._config_path)

    def _migrate_from_env(self) -> None:
        """Migrate from legacy .env fields to generate YAML."""
        try:
            from config import settings
        except Exception:
            self._config = LLMConfigFile()
            return

        providers = []
        models_created = []

        # Main LLM
        main_base_url = getattr(settings, "llm_base_url", "https://api.openai.com/v1")
        main_api_key = getattr(settings, "llm_api_key", "")
        main_model = getattr(settings, "llm_model", "gpt-4o")

        if main_api_key and main_api_key != "test_key":
            main_provider = LLMProviderConfig(
                id="default",
                name="Default Provider",
                base_url=main_base_url,
                api_key=main_api_key,
                models=[
                    LLMModelConfig(
                        id="default",
                        name=main_model,
                        model_id=main_model,
                        temperature=0.1,
                    )
                ],
            )
            providers.append(main_provider)
            models_created.append("default")

            # News LLM (if configured separately)
            news_base_url = getattr(settings, "news_llm_base_url", None)
            news_api_key = getattr(settings, "news_llm_api_key", None)
            news_model = getattr(settings, "news_llm_model", None)

            if news_model and news_model != main_model:
                # Check if it's the same provider
                if (news_base_url or main_base_url) == main_base_url and (news_api_key or main_api_key) == main_api_key:
                    # Same provider, add model
                    main_provider.models.append(
                        LLMModelConfig(
                            id="news",
                            name=f"{news_model} (News)",
                            model_id=news_model,
                            temperature=0.1,
                        )
                    )
                    models_created.append("news")
                else:
                    # Different provider
                    providers.append(LLMProviderConfig(
                        id="news-provider",
                        name="News Provider",
                        base_url=news_base_url or main_base_url,
                        api_key=news_api_key or main_api_key,
                        models=[
                            LLMModelConfig(
                                id="news",
                                name=f"{news_model} (News)",
                                model_id=news_model,
                                temperature=0.1,
                            )
                        ],
                    ))
                    models_created.append("news")

        # Build roles
        roles = LLMRolesConfig(
            agent="default" if "default" in models_created else "",
            news_filter="news" if "news" in models_created else ("default" if "default" in models_created else ""),
            memory_summary="default" if "default" in models_created else "",
        )

        config = LLMConfigFile(providers=providers, roles=roles)
        self._config = config

        if providers:
            self._write_yaml(config)
            logger.info(
                "Migrated LLM config from .env: %d providers, %d models -> %s",
                len(providers),
                sum(len(p.models) for p in providers),
                self._config_path,
            )
        else:
            logger.info("No LLM config to migrate from .env (api_key not set)")


# ============================================================
# Singleton
# ============================================================

_manager: Optional[LLMConfigManager] = None
_manager_lock = threading.Lock()


def get_llm_config_manager() -> LLMConfigManager:
    """Get the global LLM configuration manager singleton."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                from config import settings
                _manager = LLMConfigManager(data_dir=settings.data_dir)
    return _manager
