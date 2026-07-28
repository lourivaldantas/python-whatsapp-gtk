"""
Ponto de entrada: valida dependências do sistema e inicia a aplicação.
"""
import sys

_INSTALL_HINTS = """\
Dependências do sistema ausentes: {missing}

Instale conforme sua distribuição:
  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0
  Fedora:        sudo dnf install python3-gobject gtk4 webkitgtk6.0
  Arch Linux:    sudo pacman -S python-gobject gtk4 webkitgtk-6.0
"""


def _check_dependencies() -> bool:
    try:
        import gi
    except ImportError:
        sys.stderr.write(_INSTALL_HINTS.format(missing="PyGObject (módulo 'gi')"))
        return False

    missing = []
    for namespace, version in (("Gtk", "4.0"), ("WebKit", "6.0")):
        try:
            gi.require_version(namespace, version)
        except ValueError:
            missing.append(f"{namespace} {version}")
    if missing:
        sys.stderr.write(_INSTALL_HINTS.format(missing=", ".join(missing)))
        return False
    return True


def main(argv=None) -> int:
    if not _check_dependencies():
        return 1

    from .application import WhatsAppApplication

    app = WhatsAppApplication()
    return app.run(sys.argv if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
