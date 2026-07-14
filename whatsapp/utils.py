"""
Funções utilitárias: diretórios XDG e logging.
"""
import logging
import logging.handlers
import sys
from pathlib import Path

from gi.repository import GLib

from .constants import APP_NAME


def get_app_data_path() -> Path:
    """Retorna o diretório XDG de dados da aplicação, criando-o se necessário."""
    path = Path(GLib.get_user_data_dir()) / APP_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError as error:
        sys.stderr.write(f"CRITICAL: Falha ao criar diretório de dados: {error}\n")
        sys.exit(1)


def setup_logging(base_path: Path) -> None:
    """Configura logs com rotação (512 KB, 2 arquivos) e eco no terminal se interativo."""
    log_file = base_path / "application.log"

    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            str(log_file), maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
    ]
    if sys.stderr.isatty():
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
