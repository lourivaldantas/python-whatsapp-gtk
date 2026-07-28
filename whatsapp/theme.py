"""
Modo escuro automático.

Sincroniza a preferência de esquema de cores do desktop (portal XDG,
namespace org.freedesktop.appearance) com o GTK. O WebKit deriva a media
query CSS `prefers-color-scheme` dessa preferência, então o WhatsApp Web
(com tema "Padrão do sistema") acompanha o desktop em tempo real — sem
injeção de JavaScript frágil.

Funciona em GNOME, KDE e qualquer ambiente com xdg-desktop-portal. Sem
portal, cai no fallback de detectar "dark" no nome do tema GTK.
"""
import logging

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

_PORTAL_BUS = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.Settings"
_NAMESPACE = "org.freedesktop.appearance"
_KEY = "color-scheme"

# Valores da especificação: 0 = sem preferência, 1 = escuro, 2 = claro.
_SCHEME_DARK = 1


class ThemeMonitor:
    """Observa o esquema de cores do desktop e aplica no GTK (e, por tabela, no WebKit)."""

    def __init__(self) -> None:
        self._gtk_settings = Gtk.Settings.get_default()
        self._proxy = None

        if self._gtk_settings is None:
            logging.warning("Gtk.Settings indisponível; modo escuro automático desativado.")
            return

        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                _PORTAL_BUS,
                _PORTAL_PATH,
                _PORTAL_IFACE,
                None,
            )
            result = self._proxy.call_sync(
                "Read",
                GLib.Variant("(ss)", (_NAMESPACE, _KEY)),
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            scheme = result.unpack()[0]
            self._apply(scheme)
            self._proxy.connect("g-signal", self._on_portal_signal)
            logging.info("Portal de aparência conectado (esquema atual: %s).", scheme)
        except GLib.Error as error:
            logging.warning("Portal XDG indisponível (%s). Usando fallback de tema.", error.message)
            self._apply_fallback()

    def _apply(self, scheme: int) -> None:
        prefer_dark = scheme == _SCHEME_DARK
        self._gtk_settings.set_property("gtk-application-prefer-dark-theme", prefer_dark)
        logging.info("Modo escuro %s.", "ativado" if prefer_dark else "desativado")

    def _apply_fallback(self) -> None:
        theme_name = self._gtk_settings.get_property("gtk-theme-name") or ""
        if "dark" in theme_name.lower():
            self._gtk_settings.set_property("gtk-application-prefer-dark-theme", True)
            logging.info("Modo escuro ativado pelo nome do tema (%s).", theme_name)

    def _on_portal_signal(self, proxy, sender, signal_name, parameters) -> None:
        if signal_name != "SettingChanged":
            return
        namespace, key, value = parameters.unpack()
        if namespace == _NAMESPACE and key == _KEY:
            self._apply(value)
