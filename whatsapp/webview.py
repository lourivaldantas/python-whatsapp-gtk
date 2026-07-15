"""
Camada WebKit: sessão isolada, políticas de navegação, permissões e resiliência.

Todo o estado web (cookies, localStorage, IndexedDB, cache) vive no diretório
de dados da aplicação — nada se mistura com os navegadores do sistema.
"""
import base64
import json
import logging
import time
from pathlib import Path
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gio, GLib, Gtk, WebKit

from .constants import (
    ATTACH_CONFIRM_JS,
    ATTACH_PASTE_JS,
    INJECTED_STYLES,
    SPOOF_SCRIPT,
    WHATSAPP_URL,
)

# Janela de tempo para considerar crashes do WebProcess como "em sequência".
_CRASH_WINDOW_SECONDS = 60
_MAX_CRASHES_IN_WINDOW = 3

# Limite do conteúdo total por drop: os bytes viajam como base64 dentro do
# script injetado; acima disso o custo de memória fica abusivo e o botão de
# anexo do próprio WhatsApp (que lê direto do disco) é o caminho certo.
_ATTACH_MAX_BYTES = 64 * 1024 * 1024

# Quanto tempo esperar o preview de anexo abrir após o paste sintético.
_ATTACH_CONFIRM_TRIES = 12
_ATTACH_CONFIRM_INTERVAL_MS = 400

# Códigos de resultado de attach_files_to_page (além de count > 0 = sucesso).
ATTACH_FAILED = 0
ATTACH_NO_CHAT = -1
ATTACH_TOO_BIG = -2
ATTACH_BUSY = -3


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
        user_agent: str,
        chrome_major: int,
        on_load_committed: Callable[[], None],
        on_load_failed: Callable[[str], None],
        on_title_changed: Callable[[Optional[str]], None],
        on_notification: Callable[[str, str], None],
    ) -> None:
        self._base_path = base_path
        self._user_agent = user_agent
        self._chrome_major = chrome_major
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
        self._content_manager = WebKit.UserContentManager()
        style = WebKit.UserStyleSheet.new(
            INJECTED_STYLES,
            WebKit.UserContentInjectedFrames.TOP_FRAME,
            WebKit.UserStyleLevel.USER,
            None,
            None,
        )
        self._content_manager.add_style_sheet(style)
        self._register_spoof_script()

        view = WebKit.WebView(
            network_session=self.network_session,
            user_content_manager=self._content_manager,
        )
        view.set_vexpand(True)
        view.set_hexpand(True)

        self._apply_settings(view.get_settings())
        self._disable_spell_checking(view)
        self._connect_signals(view)
        return view

    def _register_spoof_script(self) -> None:
        """Registra o script anti-detecção de Safari, executado antes da página."""
        source = (
            SPOOF_SCRIPT
            .replace("__CHROME_MAJOR__", str(self._chrome_major))
            .replace("__USER_AGENT__", self._user_agent)
        )
        script = WebKit.UserScript.new(
            source,
            WebKit.UserContentInjectedFrames.ALL_FRAMES,
            WebKit.UserScriptInjectionTime.START,
            None,
            None,
        )
        self._content_manager.add_script(script)

    def _apply_settings(self, settings: WebKit.Settings) -> None:
        settings.set_user_agent(self._user_agent)
        logging.info("User-Agent definido: %s", self._user_agent)

        settings.set_enable_developer_extras(False)
        settings.set_enable_page_cache(True)

        # Os "site-specific quirks" fazem o WebKit se apresentar ao JavaScript
        # (navigator.userAgent/appVersion) como Safari de Mac em certos sites,
        # por baixo do nosso UA customizado — exatamente o que queremos evitar.
        settings.set_enable_site_specific_quirks(False)
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
        # Pré-concede a permissão de notificações: o WebKit não a persiste
        # entre sessões e, sem isso, Notification.permission fica "default"
        # e o WhatsApp exibe o banner "notificações desativadas" a cada início.
        view.get_context().connect(
            "initialize-notification-permissions",
            self._handle_init_notification_permissions,
        )
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

    def apply_user_agent(self, user_agent: str, chrome_major: int) -> None:
        """Atualiza UA e script de spoof em execução (pleno efeito no próximo load)."""
        self._user_agent = user_agent
        self._chrome_major = chrome_major
        self.view.get_settings().set_user_agent(user_agent)
        self._content_manager.remove_all_scripts()
        self._register_spoof_script()
        logging.info("User-Agent atualizado em execução: %s", user_agent)

    def attach_files_to_page(
        self, files: List[Gio.File], on_done: Optional[Callable[[int], None]] = None
    ) -> None:
        """Anexa arquivos arrastados colando-os na conversa aberta.

        O conteúdo de cada arquivo vai à página como base64 e é entregue ao
        campo de mensagem num evento "paste" sintético com objetos File reais
        (ver ATTACH_PASTE_JS) — o mesmo caminho de colar um arquivo do
        clipboard. O WhatsApp abre o preview de anexo roteando cada tipo
        (imagem vira mídia, PDF vira documento) e nada é enviado sem o usuário
        clicar em enviar. on_done recebe o nº de arquivos ou um código
        ATTACH_* negativo/zero em caso de falha.
        """
        def report(code: int) -> None:
            if on_done is not None:
                on_done(code)

        # O tamanho é conferido via stat() ANTES de ler qualquer byte: um
        # arquivo gigante jamais pode chegar à RAM (5 GB lidos aqui já
        # derrubaram o sistema via OOM killer).
        paths: list[Path] = []
        total = 0
        for gfile in files:
            raw = gfile.get_path()
            if not raw:
                continue
            path = Path(raw)
            try:
                total += path.stat().st_size
            except OSError as error:
                logging.warning("Ignorando arquivo ilegível no drop: %s (%s)", raw, error)
                continue
            if total > _ATTACH_MAX_BYTES:
                logging.info(
                    "Drop excede o limite de %d MiB por arrasto.",
                    _ATTACH_MAX_BYTES // (1024 * 1024),
                )
                report(ATTACH_TOO_BIG)
                return
            paths.append(path)

        payload = []
        for path in paths:
            try:
                # Relê o tamanho junto do conteúdo: se o arquivo cresceu entre
                # o stat() e a leitura, ainda respeitamos o limite.
                with path.open("rb") as fh:
                    data = fh.read(_ATTACH_MAX_BYTES + 1)
            except OSError as error:
                logging.warning("Ignorando arquivo ilegível no drop: %s (%s)", path, error)
                continue
            if len(data) > _ATTACH_MAX_BYTES:
                report(ATTACH_TOO_BIG)
                return
            payload.append({
                "name": path.name,
                "type": self._guess_mime(str(path)),
                "data": base64.b64encode(data).decode("ascii"),
            })
        if not payload:
            report(ATTACH_FAILED)
            return

        js = ATTACH_PASTE_JS.replace("__FILES__", json.dumps(payload))
        self.view.evaluate_javascript(
            js, -1, None, None, None,
            lambda view, result: self._on_attach_pasted(view, result, len(payload), report),
        )

    @staticmethod
    def _guess_mime(path: str) -> str:
        content_type, _ = Gio.content_type_guess(path, None)
        return Gio.content_type_get_mime_type(content_type) or "application/octet-stream"

    def _on_attach_pasted(self, view, result, count: int, report: Callable[[int], None]) -> None:
        try:
            value = view.evaluate_javascript_finish(result)
            status = value.to_string() if value is not None else ""
        except GLib.Error as error:
            logging.warning("Falha no paste sintético do anexo: %s", error.message)
            report(ATTACH_FAILED)
            return
        if status == "no-chat":
            logging.info("Drop sem conversa aberta; nada a anexar.")
            report(ATTACH_NO_CHAT)
        elif status == "busy":
            logging.info("Drop com preview de anexo já aberto; ignorado.")
            report(ATTACH_BUSY)
        elif status == "pasted":
            GLib.timeout_add(
                _ATTACH_CONFIRM_INTERVAL_MS,
                self._confirm_attach, count, report, _ATTACH_CONFIRM_TRIES,
            )
        else:
            logging.warning("Paste sintético retornou estado inesperado: %r", status)
            report(ATTACH_FAILED)

    def _confirm_attach(self, count: int, report: Callable[[int], None], tries: int) -> bool:
        """Espera o preview de anexo abrir para só então reportar sucesso."""
        def check(view, result):
            opened = False
            try:
                value = view.evaluate_javascript_finish(result)
                opened = value is not None and value.to_string() == "1"
            except GLib.Error as error:
                logging.warning("Falha ao verificar o preview de anexo: %s", error.message)
            if opened:
                logging.info("Anexo confirmado: preview aberto com %d arquivo(s).", count)
                report(count)
            elif tries <= 1:
                logging.info("Preview de anexo não abriu após o paste sintético.")
                report(ATTACH_FAILED)
            else:
                GLib.timeout_add(
                    _ATTACH_CONFIRM_INTERVAL_MS,
                    self._confirm_attach, count, report, tries - 1,
                )

        self.view.evaluate_javascript(ATTACH_CONFIRM_JS, -1, None, None, None, check)
        return GLib.SOURCE_REMOVE

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

    def _handle_init_notification_permissions(self, context: WebKit.WebContext) -> None:
        origin = WebKit.SecurityOrigin.new_for_uri(WHATSAPP_URL)
        context.initialize_notification_permissions([origin], [])
        logging.info("Permissão de notificações pré-concedida para %s", WHATSAPP_URL)

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
