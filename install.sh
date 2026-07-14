#!/bin/bash
set -u

# Cores para saída
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

APP_NAME="python-whatsapp-gtk"
APP_ID="io.github.lourivaldantas.whatsapp"
ICON_SOURCE="assets/icon.png"

INSTALL_BIN="$HOME/.local/bin"
INSTALL_SHARE="$HOME/.local/share/python-whatsapp-gtk"
INSTALL_DESKTOP="$HOME/.local/share/applications"
INSTALL_ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

print_header() {
    echo -e "${BLUE}"
    echo "=============================================="
    echo "   Python WhatsApp GTK 2.0 - Instalador"
    echo "=============================================="
    echo -e "${NC}"
}

print_status()  { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
print_error()   { echo -e "${RED}[ERRO]${NC} $1"; }

print_header

# =============================================
# VERIFICAÇÃO DAS DEPENDÊNCIAS
# =============================================

print_status "Verificando dependências..."

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 não foi encontrado."
    echo "Por favor, instale o Python 3 antes de continuar."
    exit 1
fi
print_success "Python 3 encontrado."

if ! python3 -c "import gi" 2>/dev/null; then
    print_error "Biblioteca PyGObject não encontrada."
    echo "Instale os bindings GObject para Python (ex: python3-gi ou python3-gobject)."
    exit 1
fi
print_success "PyGObject encontrado."

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0')" 2>/dev/null; then
    print_error "GTK 4 não encontrado."
    echo "  Debian/Ubuntu: sudo apt install gir1.2-gtk-4.0"
    echo "  Fedora:        sudo dnf install gtk4"
    echo "  Arch Linux:    sudo pacman -S gtk4"
    exit 1
fi
print_success "GTK 4 encontrado."

if ! python3 -c "import gi; gi.require_version('WebKit', '6.0')" 2>/dev/null; then
    print_error "WebKitGTK 6.0 não encontrado."
    echo "  Debian/Ubuntu: sudo apt install gir1.2-webkit-6.0"
    echo "  Fedora:        sudo dnf install webkitgtk6.0"
    echo "  Arch Linux:    sudo pacman -S webkitgtk-6.0"
    exit 1
fi
print_success "WebKitGTK 6.0 encontrado."

# =============================================
# PREPARAÇÃO DOS DIRETÓRIOS
# =============================================

print_status "Preparando diretórios de instalação..."
mkdir -p "$INSTALL_BIN" "$INSTALL_SHARE" "$INSTALL_DESKTOP" "$INSTALL_ICONS"

# =============================================
# LIMPEZA DE VERSÕES ANTERIORES (1.x)
# =============================================

rm -f "$INSTALL_DESKTOP/$APP_NAME.desktop"   # atalho da versão 1.x
rm -rf "$INSTALL_SHARE/whatsapp"             # pacote antigo

# =============================================
# INSTALAÇÃO DO PACOTE E EXECUTÁVEL
# =============================================

print_status "Copiando arquivos da aplicação..."

if [ -d "whatsapp" ]; then
    cp -r whatsapp "$INSTALL_SHARE/"
    find "$INSTALL_SHARE/whatsapp" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    print_success "Pacote Python copiado para $INSTALL_SHARE"
else
    print_error "Diretório 'whatsapp' não encontrado! Execute o instalador na raiz do repositório."
    exit 1
fi

print_status "Criando executável..."
cat > "$INSTALL_BIN/$APP_NAME" <<EOF
#!/bin/bash
export PYTHONPATH="$INSTALL_SHARE"
exec python3 -m whatsapp "\$@"
EOF
chmod +x "$INSTALL_BIN/$APP_NAME"
print_success "Executável instalado em $INSTALL_BIN/$APP_NAME"

# =============================================
# INSTALAÇÃO DO ÍCONE
# =============================================

if [ -f "$ICON_SOURCE" ]; then
    cp "$ICON_SOURCE" "$INSTALL_SHARE/icon.png"
    # Ícone no tema hicolor com o nome do APP_ID (usado por janela e notificações)
    cp "$ICON_SOURCE" "$INSTALL_ICONS/$APP_ID.png"
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null
    print_success "Ícone instalado."
else
    print_warning "Ícone padrão não encontrado ($ICON_SOURCE). Usando genérico."
fi

# =============================================
# CRIAÇÃO DO ATALHO
# =============================================

# O arquivo .desktop DEVE se chamar $APP_ID.desktop para que as
# notificações nativas (Gio) e o agrupamento de janelas funcionem.
cat > "$INSTALL_DESKTOP/$APP_ID.desktop" <<FIM
[Desktop Entry]
Name=WhatsApp
Comment=Cliente WhatsApp não-oficial (GTK4/WebKit)
Exec=$INSTALL_BIN/$APP_NAME
Icon=$APP_ID
Terminal=false
Type=Application
Categories=Network;Chat;InstantMessaging;
StartupNotify=true
StartupWMClass=$APP_ID
X-GNOME-UsesNotifications=true
X-GNOME-SingleWindow=true
FIM

print_success "Atalho criado em $INSTALL_DESKTOP/$APP_ID.desktop"

# =============================================
# FINALIZAÇÃO
# =============================================

update-desktop-database "$INSTALL_DESKTOP" 2>/dev/null

echo ""
echo -e "${GREEN}==============================================${NC}"
echo -e "${GREEN}      Instalação Concluída com Sucesso!       ${NC}"
echo -e "${GREEN}==============================================${NC}"
echo ""
echo "O app 'WhatsApp' deve aparecer no seu menu de aplicativos."
echo "Para desinstalar, remova:"
echo "  - $INSTALL_BIN/$APP_NAME"
echo "  - $INSTALL_SHARE"
echo "  - $INSTALL_DESKTOP/$APP_ID.desktop"
echo "  - $INSTALL_ICONS/$APP_ID.png"
echo ""
