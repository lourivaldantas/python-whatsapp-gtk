"""
Janela principal: estado persistente, zoom, tela de carregamento e de erro.
"""
import json
import logging
from typing import Any, Dict, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from .constants import (
    APP_ID,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    RETRY_SECONDS,
    WINDOW_TITLE,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STEP,
)
from .downloads import DownloadManager
from .webview import WhatsAppWebView


class WhatsAppWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title=WINDOW_TITLE)

        self._base_path = application.base_path
        self._state_file = self._base_path / "window_state.json"
        self._retry_source: Optional[int] = None
        self._retry_remaining = 0

        self.set_icon_name(APP_ID)
        state = self._load_state()
        self.set_default_size(
            int(state.get("width", DEFAULT_WIDTH)),
            int(state.get("height", DEFAULT_HEIGHT)),
        )
        if state.get("is_maximized", False):
            self.maximize()

        self.web = WhatsAppWebView(
            base_path=self._base_path,
            config=application.config,
            on_load_committed=self._show_web,
            on_load_failed=self._show_error,
            on_title_changed=self._sync_title,
            on_notification=application.notify_message,
        )
        self.web.set_zoom(float(state.get("zoom_level", 1.0)))

        self._downloads = DownloadManager(self)
        self._downloads.attach(self.web.network_session)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._stack.add_named(self._build_loading_page(), "loading")
        self._stack.add_named(self.web.view, "web")
        self._stack.add_named(self._build_error_page(), "error")
        self.set_child(self._stack)

        self.connect("close-request", self._on_close_request)

        self._stack.set_visible_child_name("loading")
        self.web.load()

    # ------------------------------------------------------------------ #
    # Páginas auxiliares

    def _build_loading_page(self) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        spinner = Gtk.Spinner(spinning=True, width_request=48, height_request=48)
        label = Gtk.Label(label="Carregando WhatsApp Web…")
        label.add_css_class("dim-label")
        box.append(spinner)
        box.append(label)
        return box

    def _build_error_page(self) -> Gtk.Widget:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        icon = Gtk.Image.new_from_icon_name("network-error-symbolic")
        icon.set_pixel_size(96)
        icon.add_css_class("dim-label")

        title = Gtk.Label(label="Falha de conexão")
        title.add_css_class("title-1")

        self._error_detail = Gtk.Label(justify=Gtk.Justification.CENTER, wrap=True)
        self._error_detail.add_css_class("dim-label")

        self._retry_label = Gtk.Label()
        self._retry_label.add_css_class("dim-label")

        retry_button = Gtk.Button(label="Tentar novamente", halign=Gtk.Align.CENTER)
        retry_button.add_css_class("suggested-action")
        retry_button.add_css_class("pill")
        retry_button.connect("clicked", lambda *_: self.reload())

        box.append(icon)
        box.append(title)
        box.append(self._error_detail)
        box.append(self._retry_label)
        box.append(retry_button)
        return box

    # ------------------------------------------------------------------ #
    # Transições de estado

    def _show_web(self) -> None:
        self._cancel_retry()
        self._stack.set_visible_child_name("web")

    def _show_error(self, message: str) -> None:
        logging.info("Exibindo tela de erro: %s", message)
        self._error_detail.set_label(f"Não foi possível carregar o WhatsApp Web.\n{message}")
        self._stack.set_visible_child_name("error")
        self._start_retry_countdown()

    def _start_retry_countdown(self) -> None:
        self._cancel_retry()
        self._retry_remaining = RETRY_SECONDS
        self._update_retry_label()
        self._retry_source = GLib.timeout_add_seconds(1, self._on_retry_tick)

    def _on_retry_tick(self) -> bool:
        self._retry_remaining -= 1
        if self._retry_remaining <= 0:
            self._retry_source = None
            self.reload()
            return GLib.SOURCE_REMOVE
        self._update_retry_label()
        return GLib.SOURCE_CONTINUE

    def _update_retry_label(self) -> None:
        self._retry_label.set_label(
            f"Nova tentativa automática em {self._retry_remaining} s"
        )

    def _cancel_retry(self) -> None:
        if self._retry_source is not None:
            GLib.source_remove(self._retry_source)
            self._retry_source = None

    def _sync_title(self, page_title: Optional[str]) -> None:
        # O WhatsApp Web coloca o nº de não lidas no título: "(3) WhatsApp".
        self.set_title(page_title or WINDOW_TITLE)

    # ------------------------------------------------------------------ #
    # Ações (invocadas pela aplicação)

    def reload(self) -> None:
        self._cancel_retry()
        self._stack.set_visible_child_name("loading")
        self.web.load()

    def zoom_in(self) -> None:
        self._set_zoom(self.web.get_zoom() + ZOOM_STEP)

    def zoom_out(self) -> None:
        self._set_zoom(self.web.get_zoom() - ZOOM_STEP)

    def zoom_reset(self) -> None:
        self._set_zoom(1.0)

    def _set_zoom(self, level: float) -> None:
        self.web.set_zoom(max(ZOOM_MIN, min(ZOOM_MAX, level)))

    def toggle_fullscreen(self) -> None:
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    # ------------------------------------------------------------------ #
    # Persistência de estado

    def _load_state(self) -> Dict[str, Any]:
        try:
            if self._state_file.exists():
                with open(self._state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if isinstance(state, dict):
                    logging.info("Estado de janela restaurado.")
                    return state
        except (OSError, ValueError) as error:
            logging.warning("Não foi possível restaurar o estado da janela: %s", error)
        return {}

    def _save_state(self) -> None:
        state = self._load_state()
        # Com a janela maximizada, width/height refletem o tamanho da tela;
        # mantemos o último tamanho "restaurado" salvo anteriormente.
        if not self.is_maximized():
            state["width"] = self.get_width() or DEFAULT_WIDTH
            state["height"] = self.get_height() or DEFAULT_HEIGHT
        state["is_maximized"] = self.is_maximized()
        state["zoom_level"] = round(self.web.get_zoom(), 2)
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
            logging.info("Estado de janela salvo.")
        except OSError as error:
            logging.warning("Erro ao salvar estado da janela: %s", error)

    def _on_close_request(self, window: Gtk.Window) -> bool:
        self._save_state()
        return False
