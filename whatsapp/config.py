"""
Gerenciamento de configuração (config.json).
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict

from .constants import LEGACY_USER_AGENTS

# user_agent: "auto" = versão do Chrome descoberta automaticamente (ver
#   useragent.py); qualquer outra string é usada literalmente como User-Agent.
# background_mode: fechar a janela mantém o app rodando em segundo plano
#   (notificações continuam chegando). Alternável com Ctrl+B.
DEFAULT_CONFIG: Dict[str, Any] = {
    "user_agent": "auto",
    "background_mode": True,
}


def load_or_create_config(base_path: Path) -> Dict[str, Any]:
    """Carrega config.json ou cria um novo com valores padrão."""
    config_file = base_path / "config.json"

    if not config_file.exists():
        _write_config(config_file, DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not isinstance(config, dict):
            raise ValueError("config.json não contém um objeto JSON")
    except (OSError, ValueError) as error:
        logging.error("Falha ao ler config.json: %s. Usando padrões.", error)
        return dict(DEFAULT_CONFIG)

    # Garante que chaves essenciais existam (merge com padrões).
    changed = False
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
            changed = True

    # Migração: User-Agents fixos gravados por versões antigas viram "auto",
    # para o usuário se beneficiar da atualização automática.
    if config.get("user_agent") in LEGACY_USER_AGENTS:
        logging.info("User-Agent antigo detectado em config.json; migrando para \"auto\".")
        config["user_agent"] = "auto"
        changed = True

    if changed:
        _write_config(config_file, config)
    return config


def save_config(base_path: Path, config: Dict[str, Any]) -> None:
    """Persiste o config atual (ex.: após alternar o modo segundo plano)."""
    _write_config(base_path / "config.json", config)


def _write_config(config_file: Path, config: Dict[str, Any]) -> None:
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logging.info("Arquivo de configuração salvo em: %s", config_file)
    except OSError as error:
        logging.error("Falha ao salvar arquivo de configuração: %s", error)
