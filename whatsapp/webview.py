"""
Camada WebKit: sessão isolada, políticas de navegação, permissões e resiliência.

Todo o estado web (cookies, localStorage, IndexedDB, cache) vive no diretório
de dados da aplicação — nada se mistura com os navegadores do sistema.
"""
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gio, GLib, Gtk, WebKit

from .constants import DEFAULT_USER_AGENT, INJECTED_STYLES, WHATSAPP_URL

# Janela de tempo para considerar crashes do WebProcess como "em sequência".
_CRASH_WINDOW_SECONDS = 60
_MAX_CRASHES_IN_WINDOW = 3


def _is_ignorable_load_error(error: GLib.Error) -> bool:
    """Erros que não representam falha real de carregamento."""
    domain = GLib.quark_to_string(error.domain)
    # Carregamento interrompido de propósito (ex.: link externo desviado ao navegador).
    if domain == "WebKitPolicyError":
        return True
    # Navegação cancelada (recarregar no meio de um load, redirecionamentos, etc.).
    if domain == "WebKitNetworkError" and error.code == WebKit.NetworkError.CANCELLED:
        return True
    return False


class WhatsAppWebView:
    """Constrói e supervisiona o WebKit.WebView do WhatsApp Web."""

    def __init__(
        self,
        base_path: Path,
        config: Dict[str, Any],
        on_load_committed: Callable[[], None],
        on_load_failed: Callable[[str], None],
        on_title_changed: Callable[[Optional[str]], None],
        on_notification: Callable[[str, str], None],
    ) -> None:
        self._base_path = base_path
        self._config = config
        self._on_load_committed = on_load_committed
        self._on_load_failed = on_load_failed
        self._on_title_changed = on_title_changed
        self._on_notification = on_notification
        self._crash_timestamps: list[float] = []

        self.network_session = self._create_network_session()
        self.view = self._create_view()

    # ------------------------------------------------------------------ #
    # Construção

    def _create_network_session(self) -> WebKit.NetworkSession:
        session = WebKit.NetworkSession.new(str(self._base_path), str(self._base_path))

        # Cookies persistentes no mesmo local usado pelas versões 1.x,
        # preservando sessões de quem atualizar.
        cookie_manager = session.get_cookie_manager()
        cookie_manager.set_persistent_storage(
            str(self._base_path / "cookies.sqlite"),
            WebKit.CookiePersistentStorage.SQLITE,
        )
        cookie_manager.set_accept_policy(WebKit.CookieAcceptPolicy.NO_THIRD_PARTY)

        # WhatsApp Web é um app de sessão longa; o ITP pode expirar storage.
        session.set_itp_enabled(False)
        return session

    def _create_view(self) -> WebKit.WebView:
        content_manager = WebKit.UserContentManager()
        style = WebKit.UserStyleSheet.new(
            INJECTED_STYLES,
            WebKit.UserContentInjectedFrames.TOP_FRAME,
            WebKit.UserStyleLevel.USER,
            None,
            None,
        )
        content_manager.add_style_sheet(style)

        view = WebKit.WebView(
            network_session=self.network_session,
            user_content_manager=content_manager,
        )
        view.set_vexpand(True)
        view.set_hexpand(True)

        self._apply_settings(view.get_settings())
        self._disable_spell_checking(view)
        self._connect_signals(view)
        return view

    def _apply_settings(self, settings: WebKit.Settings) -> None:
        user_agent = self._config.get("user_agent") or DEFAULT_USER_AGENT
        settings.set_user_agent(user_agent)
        logging.info("User-Agent definido: %s", user_agent)

        settings.set_enable_developer_extras(False)
        settings.set_enable_page_cache(True)
        settings.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.ALWAYS)

        # Necessário para mensagens de voz (microfone) e chamadas.
        settings.set_enable_media_stream(True)
        settings.set_enable_webrtc(True)

        # window.open é desviado para o navegador do sistema via sinal "create".
        settings.set_javascript_can_open_windows_automatically(True)

    def _disable_spell_checking(self, view: WebKit.WebView) -> None:
        try:
            context = view.get_context()
            context.set_spell_checking_enabled(False)
        except AttributeError:
            pass

    def _connect_signals(self, view: WebKit.WebView) -> None:
        view.connect("load-changed", self._handle_load_changed)
        view.connect("load-failed", self._handle_load_failed)
        view.connect("decide-policy", self._handle_decide_policy)
        view.connect("create", self._handle_create)
        view.connect("permission-request", self._handle_permission_request)
        view.connect("show-notification", self._handle_show_notification)
        view.connect("web-process-terminated", self._handle_web_process_terminated)
        view.connect("notify::title", self._handle_title_changed)

    # ------------------------------------------------------------------ #
    # API pública

    def load(self) -> None:
        self.view.load_uri(WHATSAPP_URL)

    def reload(self) -> None:
        self.view.reload()

    def set_zoom(self, level: float) -> None:
        self.view.set_zoom_level(level)

    def get_zoom(self) -> float:
        return self.view.get_zoom_level()

    # ------------------------------------------------------------------ #
    # Sinais

    def _handle_load_changed(self, view: WebKit.WebView, event: WebKit.LoadEvent) -> None:
        if event == WebKit.LoadEvent.COMMITTED:
            self._on_load_committed()

    def _handle_load_failed(
        self, view: WebKit.WebView, event: WebKit.LoadEvent, failing_uri: str, error: GLib.Error
    ) -> bool:
        if _is_ignorable_load_error(error):
            return False
        logging.error("Falha ao carregar %s: %s", failing_uri, error.message)
        self._on_load_failed(error.message or "Erro desconhecido")
        return True

    def _handle_decide_policy(
        self,
        view: WebKit.WebView,
        decision: WebKit.PolicyDecision,
        decision_type: WebKit.PolicyDecisionType,
    ) -> bool:
        if decision_type in (
            WebKit.PolicyDecisionType.NAVIGATION_ACTION,
            WebKit.PolicyDecisionType.NEW_WINDOW_ACTION,
        ):
            uri = decision.get_navigation_action().get_request().get_uri() or ""
            if self._is_external(uri):
                decision.ignore()
                self._open_externally(uri)
                return True
        elif decision_type == WebKit.PolicyDecisionType.RESPONSE:
            # Anexos que o WebKit não sabe exibir viram download.
            if not decision.is_mime_type_supported():
                decision.download()
                return True
        return False

    def _handle_create(
        self, view: WebKit.WebView, navigation_action: WebKit.NavigationAction
    ) -> Optional[Gtk.Widget]:
        uri = navigation_action.get_request().get_uri()
        if uri:
            self._open_externally(uri)
        return None

    @staticmethod
    def _is_external(uri: str) -> bool:
        if not uri or uri.startswith(("javascript:", "blob:", "data:", "about:")):
            return False
        try:
            host = GLib.Uri.parse(uri, GLib.UriFlags.NONE).get_host() or ""
        except GLib.Error:
            return False
        return not (host == "whatsapp.com" or host.endswith(".whatsapp.com")
                    or host == "whatsapp.net" or host.endswith(".whatsapp.net"))

    def _open_externally(self, uri: str) -> None:
        logging.info("Abrindo link externo no navegador: %.120s", uri)
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as error:
            logging.warning("Falha ao abrir link externo: %s", error.message)

    def _handle_permission_request(
        self, view: WebKit.WebView, request: WebKit.PermissionRequest
    ) -> bool:
        allowed = (
            WebKit.NotificationPermissionRequest,
            WebKit.UserMediaPermissionRequest,
            WebKit.ClipboardPermissionRequest,
            WebKit.DeviceInfoPermissionRequest,
        )
        name = type(request).__name__
        if isinstance(request, allowed):
            logging.info("Permissão concedida: %s", name)
            request.allow()
        else:
            logging.info("Permissão negada: %s", name)
            request.deny()
        return True

    def _handle_show_notification(
        self, view: WebKit.WebView, notification: WebKit.Notification
    ) -> bool:
        self._on_notification(notification.get_title() or "WhatsApp", notification.get_body() or "")
        return True

    def _handle_title_changed(self, view: WebKit.WebView, pspec) -> None:
        self._on_title_changed(view.get_title())

    def _handle_web_process_terminated(
        self, view: WebKit.WebView, reason: WebKit.WebProcessTerminationReason
    ) -> None:
        logging.error("WebProcess encerrado (%s).", reason.value_name)
        now = time.monotonic()
        self._crash_timestamps = [
            t for t in self._crash_timestamps if now - t < _CRASH_WINDOW_SECONDS
        ]
        self._crash_timestamps.append(now)

        if len(self._crash_timestamps) >= _MAX_CRASHES_IN_WINDOW:
            logging.critical("Crashes consecutivos do WebProcess; não vou recarregar de novo.")
            self._on_load_failed("O processo de renderização travou repetidamente.")
            return

        logging.info("Recarregando após queda do WebProcess...")
        GLib.idle_add(self.load)
