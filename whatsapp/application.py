"""
Aplicação GTK: instância única, ações globais, atalhos e notificações nativas.

A unicidade de instância é garantida pelo próprio Gtk.Application (D-Bus):
abrir o app de novo apenas apresenta a janela existente — sem file locks.
"""
import logging
import signal
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gio, GLib, Gtk

from . import __version__
from .config import load_or_create_config, save_config
from .constants import APP_ID, APP_NAME, WINDOW_TITLE
from .theme import ThemeMonitor
from .useragent import UserAgentResolver
from .utils import get_app_data_path, setup_logging
from .window import WhatsAppWindow


class WhatsAppApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.base_path = None
        self.config: dict = {}
        self.window: Optional[WhatsAppWindow] = None
        self._theme_monitor: Optional[ThemeMonitor] = None

    # ------------------------------------------------------------------ #

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)

        GLib.set_application_name(WINDOW_TITLE)
        self.base_path = get_app_data_path()
        setup_logging(self.base_path)
        logging.info("Iniciando %s v%s", APP_NAME, __version__)

        self.config = load_or_create_config(self.base_path)
        self.background_mode = bool(self.config.get("background_mode", True))
        self._background_notice_sent = False

        self._ua_resolver = UserAgentResolver(self.base_path, self.config)
        self.user_agent, self.chrome_major = self._ua_resolver.resolve()

        self._theme_monitor = ThemeMonitor()
        self._setup_actions()

        # Ctrl+C no terminal ou SIGTERM encerram de forma limpa (salvando estado).
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_sigint)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_sigint)

    def do_activate(self) -> None:
        if self.window is None:
            self.window = WhatsAppWindow(self)
            # Verifica em segundo plano se saiu Chrome novo (no máx. 1x/semana).
            self._ua_resolver.refresh_async(self._on_user_agent_updated)
        else:
            logging.info("Instância já em execução; apresentando janela.")
        self.window.present()

    def _on_user_agent_updated(self, user_agent: str, chrome_major: int) -> None:
        self.user_agent = user_agent
        self.chrome_major = chrome_major
        if self.window is not None:
            self.window.web.apply_user_agent(user_agent, chrome_major)

    def do_shutdown(self) -> None:
        logging.info("Encerrando aplicação.")
        Gtk.Application.do_shutdown(self)

    # ------------------------------------------------------------------ #
    # Ações e atalhos

    def _setup_actions(self) -> None:
        actions = [
            ("quit", self._on_quit, None),
            ("reload", self._on_reload, None),
            ("zoom-in", self._on_zoom_in, None),
            ("zoom-out", self._on_zoom_out, None),
            ("zoom-reset", self._on_zoom_reset, None),
            ("fullscreen", self._on_fullscreen, None),
            ("present", self._on_present, None),
            ("open-folder", self._on_open_folder, GLib.VariantType.new("s")),
        ]
        for name, callback, parameter_type in actions:
            action = Gio.SimpleAction.new(name, parameter_type)
            action.connect("activate", callback)
            self.add_action(action)

        # Ação com estado: ativá-la (Ctrl+B) alterna o booleano automaticamente.
        background = Gio.SimpleAction.new_stateful(
            "background-mode", None, GLib.Variant.new_boolean(self.background_mode)
        )
        background.connect("change-state", self._on_background_mode_changed)
        self.add_action(background)

        self.set_accels_for_action("app.background-mode", ["<Primary>b"])
        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("app.reload", ["F5", "<Primary>r"])
        self.set_accels_for_action("app.zoom-in", ["<Primary>plus", "<Primary>equal", "<Primary>KP_Add"])
        self.set_accels_for_action("app.zoom-out", ["<Primary>minus", "<Primary>KP_Subtract"])
        self.set_accels_for_action("app.zoom-reset", ["<Primary>0", "<Primary>KP_0"])
        self.set_accels_for_action("app.fullscreen", ["F11"])

    def _on_background_mode_changed(self, action, value: GLib.Variant) -> None:
        action.set_state(value)
        self.background_mode = value.get_boolean()
        self.config["background_mode"] = self.background_mode
        save_config(self.base_path, self.config)
        logging.info("Modo segundo plano %s.", "ativado" if self.background_mode else "desativado")

        if self.window is not None:
            self.window.show_toast(
                "Segundo plano ativado — fechar a janela mantém o app rodando"
                if self.background_mode
                else "Segundo plano desativado — fechar a janela encerra o app"
            )

    def _on_quit(self, action, parameter) -> None:
        if self.window is not None:
            self.window.close()
        self.quit()

    def _on_reload(self, action, parameter) -> None:
        if self.window is not None:
            logging.info("Recarregando página (atalho).")
            self.window.reload()

    def _on_zoom_in(self, action, parameter) -> None:
        if self.window is not None:
            self.window.zoom_in()

    def _on_zoom_out(self, action, parameter) -> None:
        if self.window is not None:
            self.window.zoom_out()

    def _on_zoom_reset(self, action, parameter) -> None:
        if self.window is not None:
            self.window.zoom_reset()

    def _on_fullscreen(self, action, parameter) -> None:
        if self.window is not None:
            self.window.toggle_fullscreen()

    def _on_present(self, action, parameter) -> None:
        if self.window is not None:
            self.window.present()

    def _on_open_folder(self, action, parameter) -> None:
        folder = parameter.get_string()
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(folder).get_uri(), None)
        except GLib.Error as error:
            logging.warning("Falha ao abrir pasta de download: %s", error.message)

    def _on_sigint(self) -> bool:
        logging.info("SIGINT recebido; encerrando.")
        self._on_quit(None, None)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ #
    # Notificações

    def notify_background_running(self) -> None:
        """Avisa (uma única vez por sessão) que o app segue rodando sem janela."""
        if self._background_notice_sent:
            return
        self._background_notice_sent = True
        notification = Gio.Notification.new("WhatsApp continua em segundo plano")
        notification.set_body("Clique para reabrir. Ctrl+Q encerra; Ctrl+B desativa este modo.")
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        notification.set_default_action("app.present")
        notification.set_priority(Gio.NotificationPriority.LOW)
        self.send_notification("background-info", notification)

    def notify_message(self, title: str, body: str) -> None:
        """Encaminha uma notificação do WhatsApp Web para o sistema (Gio/D-Bus)."""
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        notification.set_default_action("app.present")
        notification.set_priority(Gio.NotificationPriority.HIGH)
        self.send_notification("whatsapp-message", notification)
        logging.info("Notificação enviada ao sistema.")
