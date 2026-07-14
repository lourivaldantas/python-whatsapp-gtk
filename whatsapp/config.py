"""
Gerenciamento de configuração (config.json).
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict

from .constants import DEFAULT_USER_AGENT

DEFAULT_CONFIG: Dict[str, Any] = {
    "user_agent": DEFAULT_USER_AGENT,
}


def load_or_create_config(base_path: Path) -> Dict[str, Any]:
    """Carrega config.json ou cria um novo com valores padrão."""
    config_file = base_path / "config.json"

    if not config_file.exists():
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            logging.info("Arquivo de configuração criado em: %s", config_file)
        except OSError as error:
            logging.error("Falha ao criar arquivo de configuração: %s", error)
        return dict(DEFAULT_CONFIG)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not isinstance(config, dict):
            raise ValueError("config.json não contém um objeto JSON")
        # Garante que chaves essenciais existam (merge com padrões).
        for key, value in DEFAULT_CONFIG.items():
            config.setdefault(key, value)
        return config
    except (OSError, ValueError) as error:
        logging.error("Falha ao ler config.json: %s. Usando padrões.", error)
        return dict(DEFAULT_CONFIG)
