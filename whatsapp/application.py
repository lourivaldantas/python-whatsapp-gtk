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
from .config import load_or_create_config
from .constants import APP_ID, APP_NAME, WINDOW_TITLE
from .theme import ThemeMonitor
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
        self._theme_monitor = ThemeMonitor()
        self._setup_actions()

        # Ctrl+C no terminal ou SIGTERM encerram de forma limpa (salvando estado).
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_sigint)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_sigint)

    def do_activate(self) -> None:
        if self.window is None:
            self.window = WhatsAppWindow(self)
        else:
            logging.info("Instância já em execução; apresentando janela.")
        self.window.present()

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

        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("app.reload", ["F5", "<Primary>r"])
        self.set_accels_for_action("app.zoom-in", ["<Primary>plus", "<Primary>equal", "<Primary>KP_Add"])
        self.set_accels_for_action("app.zoom-out", ["<Primary>minus", "<Primary>KP_Subtract"])
        self.set_accels_for_action("app.zoom-reset", ["<Primary>0", "<Primary>KP_0"])
        self.set_accels_for_action("app.fullscreen", ["F11"])

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

    def notify_message(self, title: str, body: str) -> None:
        """Encaminha uma notificação do WhatsApp Web para o sistema (Gio/D-Bus)."""
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        notification.set_default_action("app.present")
        notification.set_priority(Gio.NotificationPriority.HIGH)
        self.send_notification("whatsapp-message", notification)
        logging.info("Notificação enviada ao sistema.")
