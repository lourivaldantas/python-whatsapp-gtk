#!/bin/bash
# Instalador do Python WhatsApp GTK.
#
# Uso:
#   ./install.sh              instala (ou atualiza) para o usuário atual
#   ./install.sh --uninstall  remove o app, preservando a sessão e o login
#   ./install.sh --help       mostra esta ajuda
#
# Nada aqui exige root: tudo vai para ~/.local (padrão XDG).
set -u

APP_NAME="python-whatsapp-gtk"
APP_ID="io.github.lourivaldantas.whatsapp"
ICON_SOURCE="assets/icon.png"

INSTALL_BIN="$HOME/.local/bin"
INSTALL_SHARE="$HOME/.local/share/$APP_NAME"   # também é o diretório de dados
INSTALL_DESKTOP="$HOME/.local/share/applications"
INSTALL_ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

# ---------------------------------------------------------------- aparência

# Cores e símbolos apenas em terminal interativo; em pipes/logs, texto puro.
if [ -t 1 ] && command -v tput &>/dev/null && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    BOLD="$(tput bold)" DIM="$(tput dim)" NC="$(tput sgr0)"
    RED="$(tput setaf 1)" GREEN="$(tput setaf 2)" YELLOW="$(tput setaf 3)" CYAN="$(tput setaf 6)"
    OK="${GREEN}✔${NC}" ERR="${RED}✖${NC}" WARN="${YELLOW}▲${NC}" ARROW="${CYAN}➜${NC}"
else
    BOLD="" DIM="" NC="" RED="" GREEN="" YELLOW="" CYAN=""
    OK="[OK]" ERR="[ERRO]" WARN="[AVISO]" ARROW="->"
fi

say_step()    { echo; echo "${BOLD}${CYAN}$1${NC} ${BOLD}$2${NC}"; }
say_ok()      { echo "  $OK $1"; }
say_warn()    { echo "  $WARN $1"; }
say_err()     { echo "  $ERR $1"; }
say_hint()    { echo "     ${DIM}$1${NC}"; }
die()         { say_err "$1"; [ $# -gt 1 ] && say_hint "$2"; echo; exit 1; }

banner() {
    local title="  $APP_NAME ${VERSION:+v$VERSION }— $1"
    local line
    line=$(printf '─%.0s' $(seq 1 $((${#title} + 2))))
    echo "${CYAN}╭${line}╮${NC}"
    echo "${CYAN}│${NC}${BOLD}${title}  ${NC}${CYAN}│${NC}"
    echo "${CYAN}╰${line}╯${NC}"
}

# ------------------------------------------------------------------- setup

# Sempre opera a partir da raiz do repositório, de onde quer que seja chamado.
cd "$(dirname "$(readlink -f "$0")")" || exit 1

# Versão lida direto do pacote (fonte única da verdade).
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' whatsapp/__init__.py 2>/dev/null)

usage() {
    banner "Instalador"
    echo
    echo "  ${BOLD}./install.sh${NC}              instala (ou atualiza) para o usuário atual"
    echo "  ${BOLD}./install.sh --uninstall${NC}  remove o app, preservando sessão e login"
    echo
    echo "  Instalação 100% local (~/.local) — não requer root."
    echo "  Para apagar também os dados de navegação (login, cookies, cache):"
    echo "  ${DIM}rm -rf $INSTALL_SHARE${NC}"
    echo
}

# -------------------------------------------------------------- uninstall

uninstall() {
    banner "Desinstalação"

    say_step "[1/2]" "Removendo arquivos da aplicação..."
    rm -f  "$INSTALL_BIN/$APP_NAME"              && say_ok "Executável removido."
    rm -rf "$INSTALL_SHARE/whatsapp"             && say_ok "Pacote Python removido."
    rm -f  "$INSTALL_SHARE/icon.png"
    rm -f  "$INSTALL_DESKTOP/$APP_ID.desktop"    && say_ok "Atalho do menu removido."
    rm -f  "$INSTALL_ICONS/$APP_ID.png"          && say_ok "Ícone removido."

    say_step "[2/2]" "Atualizando caches do desktop..."
    update-desktop-database "$INSTALL_DESKTOP" 2>/dev/null
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null \
        || gtk4-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null
    say_ok "Caches atualizados."

    echo
    say_ok "${BOLD}Desinstalação concluída.${NC}"
    if [ -d "$INSTALL_SHARE" ]; then
        say_warn "Sua sessão (login, cookies, config) foi ${BOLD}preservada${NC} em:"
        say_hint "$INSTALL_SHARE"
        say_hint "Para apagar tudo: rm -rf $INSTALL_SHARE"
    fi
    echo
}

# ---------------------------------------------------------------- install

check_dependency() {
    local label="$1" check="$2" hint_apt="$3" hint_dnf="$4" hint_pacman="$5"
    if eval "$check" &>/dev/null; then
        say_ok "$label"
    else
        say_err "$label não encontrado."
        say_hint "Debian/Ubuntu: sudo apt install $hint_apt"
        say_hint "Fedora:        sudo dnf install $hint_dnf"
        say_hint "Arch Linux:    sudo pacman -S $hint_pacman"
        MISSING=1
    fi
}

install_app() {
    if [ -x "$INSTALL_BIN/$APP_NAME" ]; then
        banner "Atualização"
    else
        banner "Instalador"
    fi

    # ----------------------------------------------------- 1. dependências
    say_step "[1/5]" "Verificando dependências..."
    MISSING=0
    check_dependency "Python 3" \
        "command -v python3" \
        "python3" "python3" "python"
    check_dependency "PyGObject" \
        "python3 -c 'import gi'" \
        "python3-gi" "python3-gobject" "python-gobject"
    check_dependency "GTK 4" \
        "python3 -c \"import gi; gi.require_version('Gtk', '4.0')\"" \
        "gir1.2-gtk-4.0" "gtk4" "gtk4"
    check_dependency "WebKitGTK 6.0" \
        "python3 -c \"import gi; gi.require_version('WebKit', '6.0')\"" \
        "gir1.2-webkit-6.0" "webkitgtk6.0" "webkitgtk-6.0"
    [ "$MISSING" -eq 0 ] || die "Instale as dependências acima e rode o instalador de novo."

    [ -d "whatsapp" ] || die "Diretório 'whatsapp' não encontrado." \
                             "Execute o instalador na raiz do repositório."

    # ------------------------------------------------------- 2. app files
    say_step "[2/5]" "Copiando arquivos da aplicação..."
    mkdir -p "$INSTALL_BIN" "$INSTALL_SHARE" "$INSTALL_DESKTOP" "$INSTALL_ICONS"

    # Resíduos da série 1.x (atalho antigo) e da instalação anterior.
    rm -f "$INSTALL_DESKTOP/$APP_NAME.desktop"
    rm -rf "$INSTALL_SHARE/whatsapp"

    cp -r whatsapp "$INSTALL_SHARE/" || die "Falha ao copiar o pacote Python."
    find "$INSTALL_SHARE/whatsapp" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    say_ok "Pacote Python ${VERSION:+v$VERSION }em ${DIM}$INSTALL_SHARE/whatsapp${NC}"

    # ------------------------------------------------------ 3. executável
    say_step "[3/5]" "Criando executável..."
    cat > "$INSTALL_BIN/$APP_NAME" <<EOF
#!/bin/bash
export PYTHONPATH="$INSTALL_SHARE"
exec python3 -m whatsapp "\$@"
EOF
    chmod +x "$INSTALL_BIN/$APP_NAME"
    say_ok "Executável em ${DIM}$INSTALL_BIN/$APP_NAME${NC}"
    case ":$PATH:" in
        *":$INSTALL_BIN:"*) ;;
        *) say_warn "$INSTALL_BIN não está no seu PATH (o atalho do menu funciona mesmo assim)." ;;
    esac

    # ----------------------------------------------------------- 4. ícone
    say_step "[4/5]" "Instalando ícone..."
    if [ -f "$ICON_SOURCE" ]; then
        cp "$ICON_SOURCE" "$INSTALL_SHARE/icon.png"
        # No tema hicolor com o nome do APP_ID: usado pela janela e notificações.
        cp "$ICON_SOURCE" "$INSTALL_ICONS/$APP_ID.png"
        gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null \
            || gtk4-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null
        say_ok "Ícone instalado no tema hicolor."
    else
        say_warn "Ícone não encontrado ($ICON_SOURCE); o sistema usará um genérico."
    fi

    # ---------------------------------------------------------- 5. atalho
    say_step "[5/5]" "Criando atalho no menu..."
    # O arquivo DEVE se chamar $APP_ID.desktop: é assim que as notificações
    # nativas (Gio) e o agrupamento de janelas encontram o app.
    cat > "$INSTALL_DESKTOP/$APP_ID.desktop" <<FIM
[Desktop Entry]
Name=WhatsApp
Comment=Unofficial WhatsApp client (GTK4/WebKitGTK)
Comment[pt_BR]=Cliente WhatsApp não-oficial (GTK4/WebKitGTK)
Keywords=whatsapp;chat;messaging;zap;
Exec=$INSTALL_BIN/$APP_NAME
Icon=$APP_ID
Terminal=false
Type=Application
Categories=Network;Chat;InstantMessaging;
StartupNotify=true
StartupWMClass=$APP_ID
X-GNOME-UsesNotifications=true
X-GNOME-SingleWindow=true
SingleMainWindow=true
FIM
    update-desktop-database "$INSTALL_DESKTOP" 2>/dev/null
    say_ok "Atalho em ${DIM}$INSTALL_DESKTOP/$APP_ID.desktop${NC}"

    # ------------------------------------------------------------- resumo
    echo
    echo "${GREEN}${BOLD}  Instalação concluída com sucesso!${NC}"
    echo
    echo "  $ARROW Procure por ${BOLD}WhatsApp${NC} no menu de aplicativos."
    echo "  $ARROW Ou rode no terminal: ${BOLD}$APP_NAME${NC}"
    echo "  $ARROW Para desinstalar:    ${BOLD}./install.sh --uninstall${NC}"
    echo
    echo "  ${DIM}Sessão, configuração e logs: $INSTALL_SHARE${NC}"
    echo
}

# ------------------------------------------------------------------- main

case "${1:-}" in
    "")                 install_app ;;
    --uninstall|-u)     uninstall ;;
    --help|-h)          usage ;;
    *)                  usage; die "Opção desconhecida: $1" ;;
esac
