"""
Constantes do Python WhatsApp GTK.
"""

# Identidade da aplicação (o ID também define a instância única no D-Bus
# e o nome do arquivo .desktop usado pelas notificações do GNOME).
APP_ID = "io.github.lourivaldantas.whatsapp"
APP_NAME = "python-whatsapp-gtk"
WINDOW_TITLE = "WhatsApp"

DEFAULT_WIDTH = 1100
DEFAULT_HEIGHT = 720

WHATSAPP_URL = "https://web.whatsapp.com/"

# O WhatsApp Web rejeita o User-Agent padrão do WebKit ("navegador não
# suportado"), então nos apresentamos como um Chrome atual no Linux.
# Pode ser sobrescrito em config.json.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

# CSS injetado para ocultar banners de upsell ("Baixe o app") e limpar a interface.
INJECTED_STYLES = """
    svg[viewBox="0 0 228 152"] { display: none !important; }

    h1.html-h1 { display: none !important; }
    h1.html-h1 ~ div button { display: none !important; }

    div:has(> h1.html-h1) { display: none !important; }

    span[data-icon="wa-square-icon"] { display: none !important; }

    div[role="button"]:has(span[data-icon="wa-square-icon"]) { display: none !important; }

    div[role="button"]:has(> div > span[data-icon="wa-square-icon"]) { display: none !important; }

    div:has(> div > span[data-icon="web-login-desktop-upsell-illustration"]) { display: none !important; }

    div:has(> div > div > span[data-icon="web-login-desktop-upsell-illustration"]) { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }

    div:has(> div > div > div > span[data-icon="web-login-desktop-upsell-illustration"]) { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
"""

# Limites de zoom da página.
ZOOM_MIN = 0.5
ZOOM_MAX = 2.5
ZOOM_STEP = 0.1

# Segundos até a tentativa automática de reconexão após falha de rede.
RETRY_SECONDS = 10
