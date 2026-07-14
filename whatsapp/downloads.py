"""
Gerenciador de downloads.

Intercepta downloads da sessão de rede do WebKit, pergunta onde salvar via
Gtk.FileDialog (assíncrono, com suporte a portais) e notifica o resultado.
"""
import logging
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gio, GLib, Gtk, WebKit

# Código de WebKitDownloadError quando o próprio usuário cancela.
_DOWNLOAD_CANCELLED_BY_USER = 400


class DownloadManager:
    def __init__(self, window: Gtk.Window) -> None:
        self._window = window

    def attach(self, network_session: WebKit.NetworkSession) -> None:
        network_session.connect("download-started", self._on_download_started)

    # ------------------------------------------------------------------ #

    def _on_download_started(self, session: WebKit.NetworkSession, download: WebKit.Download) -> None:
        uri = download.get_request().get_uri() if download.get_request() else "?"
        logging.info("Download iniciado: %.120s", uri)
        download.connect("decide-destination", self._on_decide_destination)
        download.connect("finished", self._on_finished)
        download.connect("failed", self._on_failed)

    def _on_decide_destination(self, download: WebKit.Download, suggested_filename: str) -> bool:
        dialog = Gtk.FileDialog(title="Salvar arquivo")
        dialog.set_initial_name(suggested_filename or "whatsapp_download")

        downloads_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads_dir:
            dialog.set_initial_folder(Gio.File.new_for_path(downloads_dir))

        dialog.save(self._window, None, self._on_dialog_finished, download)
        # True + destino definido depois: o download fica pausado até a escolha.
        return True

    def _on_dialog_finished(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, download: WebKit.Download) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            logging.info("Download cancelado pelo usuário.")
            download.cancel()
            return

        path = gfile.get_path()
        if not path:
            logging.warning("Destino sem caminho local; cancelando download.")
            download.cancel()
            return

        logging.info("Destino do download: %s", path)
        download.set_destination(path)

    # ------------------------------------------------------------------ #

    def _on_finished(self, download: WebKit.Download) -> None:
        destination = download.get_destination() or ""
        filename = Path(destination).name if destination else "arquivo"
        logging.info("Download concluído: %s", destination)

        app = self._window.get_application()
        if app is None:
            return
        notification = Gio.Notification.new("Download concluído")
        notification.set_body(f"“{filename}” foi salvo com sucesso.")
        notification.set_icon(Gio.ThemedIcon.new("document-save-symbolic"))
        if destination:
            folder = str(Path(destination).parent)
            notification.add_button_with_target(
                "Abrir pasta", "app.open-folder", GLib.Variant("s", folder)
            )
        app.send_notification("download-finished", notification)

    def _on_failed(self, download: WebKit.Download, error: GLib.Error) -> None:
        if error.code == _DOWNLOAD_CANCELLED_BY_USER:
            return
        logging.warning("Download falhou: %s", error.message)

        app = self._window.get_application()
        if app is None:
            return
        notification = Gio.Notification.new("Falha no download")
        notification.set_body(error.message or "Erro desconhecido.")
        notification.set_icon(Gio.ThemedIcon.new("dialog-error-symbolic"))
        app.send_notification("download-failed", notification)
