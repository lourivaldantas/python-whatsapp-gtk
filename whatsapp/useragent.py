"""
User-Agent automático.

O WhatsApp Web exige um navegador "suportado", e um User-Agent de Chrome
com versão antiga acaba rejeitado com o tempo. Este módulo descobre a
versão estável atual do Chrome pela API oficial VersionHistory do Google
(uma requisição leve, sem cookies, no máximo uma vez por semana), guarda
em cache e monta o User-Agent. Sem rede, usa o cache; sem cache, usa o
fallback embutido.

Um valor fixo em config.json ("user_agent": "Mozilla/...") desativa
totalmente a descoberta automática — inclusive a requisição de rede.
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import gi

gi.require_version("Soup", "3.0")
from gi.repository import GLib, Gio, Soup

from .constants import (
    CHROME_VERSION_API,
    FALLBACK_CHROME_MAJOR,
    USER_AGENT_TEMPLATE,
)

_CACHE_FILE = "ua_cache.json"
_CACHE_MAX_AGE = 7 * 24 * 3600  # 7 dias
_CHROME_MAJOR_RE = re.compile(r"Chrome/(\d+)")


def build_user_agent(chrome_major: int) -> str:
    return USER_AGENT_TEMPLATE.format(major=chrome_major)


def extract_chrome_major(user_agent: str) -> int:
    """Extrai a versão principal do Chrome de um UA (para o script de spoof)."""
    match = _CHROME_MAJOR_RE.search(user_agent or "")
    return int(match.group(1)) if match else FALLBACK_CHROME_MAJOR


class UserAgentResolver:
    """Resolve o User-Agent na inicialização e o atualiza em segundo plano."""

    def __init__(self, base_path: Path, config: Dict) -> None:
        self._cache_file = base_path / _CACHE_FILE
        self._custom_ua: Optional[str] = None

        configured = (config.get("user_agent") or "auto").strip()
        if configured and configured.lower() != "auto":
            self._custom_ua = configured

    # ------------------------------------------------------------------ #

    def resolve(self) -> Tuple[str, int]:
        """Retorna (user_agent, chrome_major) imediatamente, sem rede."""
        if self._custom_ua:
            logging.info("User-Agent fixo definido em config.json; descoberta automática desativada.")
            return self._custom_ua, extract_chrome_major(self._custom_ua)

        major = max(self._read_cache()[0] or 0, FALLBACK_CHROME_MAJOR)
        return build_user_agent(major), major

    def refresh_async(self, on_updated: Callable[[str, int], None]) -> None:
        """Consulta a versão atual do Chrome; chama on_updated se ela mudou."""
        if self._custom_ua:
            return

        cached_major, checked_at = self._read_cache()
        if cached_major and (time.time() - checked_at) < _CACHE_MAX_AGE:
            logging.info("Cache de User-Agent ainda válido (Chrome %s).", cached_major)
            return

        logging.info("Consultando versão estável atual do Chrome...")
        session = Soup.Session(timeout=15)
        message = Soup.Message.new("GET", CHROME_VERSION_API)
        session.send_and_read_async(
            message,
            GLib.PRIORITY_LOW,
            None,
            self._on_response,
            (message, on_updated),
        )

    # ------------------------------------------------------------------ #

    def _on_response(self, session: Soup.Session, result: Gio.AsyncResult, data) -> None:
        message, on_updated = data
        try:
            body = session.send_and_read_finish(result)
            if message.get_status() != Soup.Status.OK:
                raise ValueError(f"HTTP {message.get_status()}")
            payload = json.loads(body.get_data().decode("utf-8"))
            version = payload["versions"][0]["version"]
            major = int(version.split(".")[0])
        except (GLib.Error, ValueError, KeyError, IndexError) as error:
            logging.warning("Falha ao consultar versão do Chrome (%s); mantendo atual.", error)
            return

        previous, _ = self._read_cache()
        self._write_cache(major)

        if major != (previous or FALLBACK_CHROME_MAJOR):
            logging.info("Nova versão do Chrome detectada: %s. Atualizando User-Agent.", major)
            on_updated(build_user_agent(major), major)
        else:
            logging.info("User-Agent já atualizado (Chrome %s).", major)

    # ------------------------------------------------------------------ #

    def _read_cache(self) -> Tuple[Optional[int], float]:
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            return int(cache["chrome_major"]), float(cache.get("checked_at", 0))
        except (OSError, ValueError, KeyError):
            return None, 0.0

    def _write_cache(self, major: int) -> None:
        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump({"chrome_major": major, "checked_at": time.time()}, f, indent=4)
        except OSError as error:
            logging.warning("Falha ao gravar cache de User-Agent: %s", error)
