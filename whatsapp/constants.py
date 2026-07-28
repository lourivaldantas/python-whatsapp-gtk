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
# A versão do Chrome é descoberta automaticamente (ver useragent.py);
# um valor fixo pode ser definido em config.json no lugar de "auto".
USER_AGENT_TEMPLATE = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
)

# Usado quando não há cache nem rede na primeira execução.
FALLBACK_CHROME_MAJOR = 150

# API oficial do Google com o histórico de versões do Chrome.
CHROME_VERSION_API = (
    "https://versionhistory.googleapis.com/v1/chrome/platforms/linux/"
    "channels/stable/versions?pageSize=1"
)

# User-Agents fixos gravados em config.json por versões antigas do app;
# ao encontrá-los, migramos para "auto".
LEGACY_USER_AGENTS = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
)

# Script injetado em document-start para o WhatsApp Web não detectar o
# WebKit como "Safari/Mac" via JavaScript: corrige navigator.vendor,
# navigator.userAgent/appVersion (os quirks do WebKit os reportam como
# Safari de Mac mesmo com UA customizado), fornece navigator.userAgentData
# (client hints, exclusivo de Chromium), um window.chrome mínimo e mascara
# o renderizador WebGL "Apple GPU". Os placeholders __CHROME_MAJOR__ e
# __USER_AGENT__ são substituídos em tempo de execução.
SPOOF_SCRIPT = """
(function () {
    'use strict';
    var MAJOR = '__CHROME_MAJOR__';
    var UA = '__USER_AGENT__';

    function define(target, prop, value) {
        try {
            Object.defineProperty(target, prop, {
                get: function () { return value; },
                configurable: true
            });
        } catch (e) { /* propriedade blindada; segue o jogo */ }
    }

    define(Navigator.prototype, 'vendor', 'Google Inc.');
    define(Navigator.prototype, 'userAgent', UA);
    define(Navigator.prototype, 'appVersion', UA.replace(/^Mozilla\\//, ''));

    var brands = [
        { brand: 'Chromium', version: MAJOR },
        { brand: 'Google Chrome', version: MAJOR },
        { brand: 'Not;A=Brand', version: '99' }
    ];
    var fullVersionList = brands.map(function (b) {
        return { brand: b.brand, version: MAJOR + '.0.0.0' };
    });
    var uaData = {
        brands: brands,
        mobile: false,
        platform: 'Linux',
        getHighEntropyValues: function () {
            return Promise.resolve({
                architecture: 'x86',
                bitness: '64',
                brands: brands,
                fullVersionList: fullVersionList,
                mobile: false,
                model: '',
                platform: 'Linux',
                platformVersion: '6.1.0',
                uaFullVersion: MAJOR + '.0.0.0'
            });
        },
        toJSON: function () {
            return { brands: brands, mobile: false, platform: 'Linux' };
        }
    };
    define(Navigator.prototype, 'userAgentData', uaData);

    if (!window.chrome) {
        try {
            window.chrome = { runtime: {}, loadTimes: function () {}, csi: function () {} };
        } catch (e) { }
    }

    // O WebKit reporta o renderizador WebGL como "Apple GPU", entregando
    // que somos Safari. Respondemos como um Chrome/ANGLE típico no Linux.
    var GL_VENDOR = 'Google Inc. (Intel)';
    var GL_RENDERER = 'ANGLE (Intel, Mesa Intel(R) UHD Graphics (ADL GT2), OpenGL ES 3.2)';
    function patchGL(proto) {
        if (!proto || !proto.getParameter) { return; }
        var original = proto.getParameter;
        proto.getParameter = function (pname) {
            // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL
            if (pname === 0x9245) { return GL_VENDOR; }
            if (pname === 0x9246) { return GL_RENDERER; }
            return original.apply(this, arguments);
        };
    }
    if (window.WebGLRenderingContext) { patchGL(WebGLRenderingContext.prototype); }
    if (window.WebGL2RenderingContext) { patchGL(WebGL2RenderingContext.prototype); }
})();
"""

# Cola arquivos arrastados na conversa aberta como um "paste" sintético.
#
# Por que assim: o drag and drop nativo do WebKitGTK entrega à página um drop
# com dataTransfer.files VAZIO (o arquivo vem só como text/uri-list), inútil
# para o WhatsApp. E acionar o menu de anexo (botão "+") com cliques sintéticos
# se mostrou não confiável — o menu muitas vezes não abre. Já o handler de
# PASTE do WhatsApp aceita File sintéticos: construímos os arquivos em JS
# (conteúdo em base64), montamos um DataTransfer e disparamos um ClipboardEvent
# no campo de mensagem — o mesmo caminho de colar um arquivo do clipboard.
# O próprio WhatsApp abre o preview de anexo e roteia cada tipo (imagem vira
# mídia, PDF vira documento); nada é enviado sem o usuário confirmar.
# __FILES__ vira um JSON [{name, type, data}].
ATTACH_PASTE_JS = r"""
(function (files) {
    var icons = document.querySelectorAll('span[data-icon="wds-ic-send-filled"], span[data-icon="send"]');
    for (var i = 0; i < icons.length; i++) {
        if (!icons[i].closest('#main')) { return 'busy'; }
    }
    var box = document.querySelector('#main footer [contenteditable="true"]')
           || document.querySelector('#main footer [role="textbox"]');
    if (!box) { return 'no-chat'; }
    var dt = new DataTransfer();
    for (var i = 0; i < files.length; i++) {
        var bin = atob(files[i].data);
        var bytes = new Uint8Array(bin.length);
        for (var j = 0; j < bin.length; j++) { bytes[j] = bin.charCodeAt(j); }
        dt.items.add(new File([bytes], files[i].name, { type: files[i].type }));
    }
    box.focus();
    var ev = new ClipboardEvent('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(ev, 'clipboardData', { value: dt });
    box.dispatchEvent(ev);
    return 'pasted';
})(__FILES__)
"""

# Detecta o preview de anexo aberto: o botão de enviar do preview fica FORA
# do #main (overlay), enquanto o de mensagem de texto fica dentro do rodapé
# do #main — critério estrutural, independente do idioma da interface.
ATTACH_CONFIRM_JS = """
(function () {
    var icons = document.querySelectorAll('span[data-icon="wds-ic-send-filled"], span[data-icon="send"]');
    for (var i = 0; i < icons.length; i++) {
        if (!icons[i].closest('#main')) { return '1'; }
    }
    return '0';
})()
"""

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
