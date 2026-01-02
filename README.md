# Python WhatsApp GTK
> Um jeito simples de usar o WhatsApp no Linux.

![Screenshot do App](assets/screenshot.png)

## Sobre o Projeto
Sempre prezei pelo equilíbrio entre **privacidade, segurança e conforto**. 

Embora achasse interessante a função **PWA** (Progressive Web App) de navegadores populares como Chrome ou Edge, abandonei o uso deles justamente por questões de privacidade e coleta de dados dos próprios navegadores. Além disso, apesar de saber da excelência de vários *ports* e *wrappers* feitos pela comunidade, resolvi criar minha própria solução:

Fiz um **wrapper** em **Python** — linguagem com a qual tenho familiaridade — utilizando o **WebKit2**, que gera um ambiente **sandbox** isolado e sem telemetria por parte dos navegadores. 

> *"Recomendo a todos que criem vocês mesmos seus programas desse tipo. Caso não queiram, aí está o meu: transparente e auditável."*

## Funcionalidades
- Navegador WebKit.
- Isolamento de dados.
- Instalação integrada ao menu do sistema.
- Suporte a gestos (padrão WebKit).

## Pré-requisitos
Para instalar o wrapper, você precisa do Git, Python 3 e das bibliotecas do sistema do GTK, WebKit e notificações. Escolha o comando de acordo com sua distribuição:

### Debian / Ubuntu / Pop!_OS
```bash
sudo apt update
sudo apt install -y git python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-notify-0.7 libnotify-bin
```

### Fedora / Red Hat / CentOS
```bash
sudo dnf install git python3 python3-gobject python3-cairo gtk3 webkit2gtk4.1 libnotify
```

### Arch Linux / Manjaro / EndeavourOS
```bash
sudo pacman -S git python python-gobject python-cairo gtk3 webkit2gtk-4.1 libnotify
```

### Slackware
```bash
sudo slackpkg update
sudo slackpkg install git python3 pygobject3 pycairo gtk+3 webkit2gtk libnotify
```
### Dicionário
| **Componente** | **Debian/Ubuntu** | **Fedora** | **Arch Linux** | **Slackware** 
| :---: | :---: | :---: | :---: | :---:
| **GIT** | git | git | git | git
| **Linguagem** | python3 | python3 | python | python3
| **Bindings GObject** | python3-gi | python3-gobject | python-gobject | pygobject3
| **Bindings Cairo** | python3-gi-cairo | python3-cairo | python-cairo | pycairo
| **GTK 3** | gir1.2-gtk-3.0 | gtk3 | gtk3 | gtk+3
| **WebKit 4.1** | gir1.2-webkit2-4.1 | webkit2gtk4.1 | webkit2gtk4.1 | webkit2gtk
| **Notificações** | gir1.2-notify-0.7 libnotify-bin | libnotify | libnotify | libnotify
## Instalação e uso
### 1. Clone o repositório:
```bash
git clone https://github.com/lourivaldantas/python-whatsapp-gtk.git
cd python-whatsapp-gtk
```

### 2. Execute o instalador
```bash
chmod +x install.sh
./install.sh
```

## Desinstalação do programa:
```bash
# Remove o executável e o atalho
rm ~/.local/bin/python-whatsapp-gtk
rm ~/.local/share/applications/python-whatsapp-gtk.desktop
# Remove os dados de navegação (Login, Cache, Cookies)
rm -rf ~/.local/share/python-whatsapp-gtk
```

## Como funciona
Diferente de aplicações baseadas em Electron (que embutem um navegador Chromium inteiro para cada app, consumindo muita RAM), este projeto utiliza as bibliotecas nativas do seu sistema Linux.

A arquitetura funciona em três camadas:
1. Backend (Lógica): O Python 3 gerencia a criação da janela e o isolamento dos dados.
2. Ponte (Bindings): O PyGObject (GObject Introspection) conecta o código Python diretamente às bibliotecas C/C++ do sistema GNOME.
3. Engine (Renderização): O WebKit2 (mesmo motor do Safari) renderiza o WhatsApp Web.

O Diferencial: Isolamento de Dados: O script força o WebKit a criar um contexto de dados ("perfil") exclusivo dentro da pasta ~/.local/share/python-whatsapp-gtk. Isso garante que:
- Seus cookies do WhatsApp não se misturam com seu navegador principal.
- Você tem portabilidade total (basta copiar a pasta para fazer backup da sessão).

## Licença
Este projeto é desenvolvido sob a Licença Pública Geral GNU v3.0 (GPLv3).

Isso significa que você tem a liberdade de:

- Usar o software para qualquer finalidade.
- Estudar como o programa funciona e adaptá-lo às suas necessidades.
- Redistribuir cópias de modo que você possa ajudar ao seu próximo.
- Aperfeiçoar o programa e liberar os seus aperfeiçoamentos, de modo que toda a comunidade se beneficie.

Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
