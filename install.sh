#!/bin/bash

SOURCE_FILE="python-whatsapp-gtk.py"
APP_NAME="python-whatsapp-gtk"
ICON_SOURCE="assets/icon.png"

INSTALL_BIN="$HOME/.local/bin"
INSTALL_SHARE="$HOME/.local/share/python-whatsapp-gtk"
INSTALL_DESKTOP="$HOME/.local/share/applications"

echo "Iniciando a instalação do Python WhatsApp GTK."

# =============================================
# VERIFICAÇÃO DAS DEPENDÊNCIAS
# =============================================

echo "Verificando dependências..."

if ! command -v python3 &> /dev/null; then
    echo "Python 3 não foi encontrado. Instale-o primeiro."
    echo "Confira o README.md para ver como instalar em sua distribuição Linux."
    exit 1
fi

python3 -c "import gi" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "A biblioteca PyGObject (GTK para Python) não foi encontrada. Instale-a primeiro."
    echo "Confira o README.md para ver como instalar em sua distribuição Linux."
    exit 1
fi

# =============================================
# PREPARAÇÃO DOS DIRETÓRIOS
# =============================================

mkdir -p "$INSTALL_BIN"
mkdir -p "$INSTALL_SHARE"
mkdir -p "$INSTALL_DESKTOP"

# =============================================
# INSTALAÇÃO DO EXECUTÁVEL
# =============================================

if [ ! -f "$SOURCE_FILE" ]; then
    echo "Erro. Arquivo $SOURCE_FILE não foi encontrado na pasta atual."
    echo "Certifique-se de estar rodando o install.sh na pasta raiz do projeto."
    exit 1
fi

echo "Instalando o executável em $INSTALL_BIN."
cp "$SOURCE_FILE" "$INSTALL_BIN/$APP_NAME"
chmod +x "$INSTALL_BIN/$APP_NAME"

# =============================================
# INSTALAÇÃO DO ÍCONE
# =============================================

if [ -f "$ICON_SOURCE" ]; then
    echo "Copiando ícone para $INSTALL_SHARE"
    cp "$ICON_SOURCE" "$INSTALL_SHARE/icon.png"
else
    echo "Aviso: Ícone não encontrado. Usando ícone genérico."
fi

# =============================================
# CRIAÇÃO DO ATALHO
# =============================================

cat > "$INSTALL_DESKTOP/$APP_NAME.desktop" <<FIM
[Desktop Entry]
Name=WhatsApp
Comment=Cliente WhatsApp não-oficial
Exec=$INSTALL_BIN/$APP_NAME
Icon=$INSTALL_SHARE/icon.png
Terminal=false
Type=Application
Categories=Network;Chat;
StartupWMClass=whatsapp
X-GNOME-SingleWindow=true
FIM

# =============================================
# FINALIZAÇÃO
# =============================================

# Atualiza o banco de dados do ambiente gráfico para reconhecer o novo app
update-desktop-database "$INSTALL_DESKTOP" 2>/dev/null

echo "Instalação concluída com sucesso!"
echo "O app 'WhatsApp' deve aparecer no seu menu de aplicativos em instantes."
echo "Para desinstalar, basta remover os arquivos criados em ~/.local/"
