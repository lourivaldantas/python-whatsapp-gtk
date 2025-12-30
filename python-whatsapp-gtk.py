#!/usr/bin/env python3
"""
Python WhatsApp GTK
-------------------
Um cliente não-oficial e leve para o WhatsApp Web utilizando Webkit2 e GTK3.
Destaques:
- Economia de recursos (RAM/CPU) comparado a navegadores completos.
- Sessão isolada: não mistura cookies/cache com seu navegador principal.
- Integração com o ambiente gráfico Linux (GNOME/XDG).

Autor: Lourival Dantas
Licença: GPLv3
"""

import fcntl
import gi
import json
import logging
import os
import sys
import urllib.request

# Garante que as versões corretas das bibliotecas do sistema operacional sejam carregadas.
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib

def get_latest_user_agent():
    """
    Busca o User_Agent mais recente para evitar manutenção manual constante.
    Usa biblioteca nativa para não aumentar o consumo de RAM.
    """
    fallback_ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    url = "https://jnrbsn.github.io/user-agents/user-agents.json"

    try:
        # Timeout curto para não travar a inicialização se estiver sem internet.
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data and len(data) > 0:
                # Retorna o primeiro da list (geralmente o mais novo/popular)
                logging.info(f"User-Agent atualizado via nuvem {data[0]}")
                return data[0]
    except Exception as error:
        logging.warning(f"Falha ao buscar User-Agent on-line ({error}).")
    
    # Se der erro ou se a lista vier vazia, apenas retorna o fallback.
    return fallback_ua

def get_app_data_path():
    # Retorna o diretório padrão do usuário (XDG Standard)
    path = os.path.join(GLib.get_user_data_dir(), "python-whatsapp-gtk")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError as error:
        sys.stderr.write(f"CRITICAL: Falha ao criar repositório de dados: {error}\n")
        sys.exit(1)

class ClientWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="WhatsApp")
        
        self.base_path = get_app_data_path()
        self.state_file = os.path.join(self.base_path, "window_state.json")

        # Cria um arquivo de trava. Se já estiver trancado por outro, fecha este.
        self.lock_file_path = os.path.join(self.base_path, "app.lock")
        
        try:
            self.lock_fp = open(self.lock_file_path, 'w')
            # Tenta adquirir bloqueio exclusivo (LOCK_EX) e sem esperar (LOCK_NB).
            fcntl.lockf(self.lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            logging.warning("Outra instância já está rodando. Encerrando")
            sys.exit(0)

        if not self.load_window_state():
            self.set_default_size(1000, 700)

        log_file = os.path.join(self.base_path, "application.log")

        # Salva logs em arquivos para auditoria.
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        try:
            # isola cookies e cache na pasta "wtp_data", sem misturar com o navegador do sistema operacional.
            data_manager = WebKit2.WebsiteDataManager(
                base_data_directory = self.base_path,
                base_cache_directory = self.base_path
            )

            context = WebKit2.WebContext.new_with_website_data_manager(data_manager)

            # Otimiza o gerenciamento de RAM para Single SPA.
            context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
            # Desativa o corretor ortográfico para economizar RAM
            context.set_spell_checking_enabled(False)

            self.webview = WebKit2.WebView.new_with_context(context)

            # ----- WebView Connect -----
            self.connect("delete-event", self.save_window_state)
            self.webview.connect("decide-policy", self._on_decide_policy) # Evita que links externos sejam abertos no wrapper.
            self.webview.connect("create", self._on_create_web_view) # Captura tentativas de abrir novas janelas por JavaScript e redireciona para o navegador padrão.
            self.webview.connect("permission-request", self._on_permission_request) # Gerencia as permissões de microfone e câmera.

            # Aplica o User Agent "falso" para passar pelo filtro do WhatsApp.
            settings = self.webview.get_settings()

            settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ALWAYS)

            settings.set_enable_write_console_messages_to_stdout(False) # Limpa o terminal,
            settings.set_enable_developer_extras(False) # Desativa funções de desenvolvedor, economizando memória.

            latest_ua = get_latest_user_agent()
            settings.set_user_agent(latest_ua)

            # Carrega a aplicação
            url = "https://web.whatsapp.com/"
            self.webview.load_uri(url)
            self.add(self.webview)
        except Exception as error:
            # Captura falhas na engine do navegador.
            logging.critical(f"Erro fatal ao iniciar WebKit: {error}", exc_info=True)
            raise error

    def save_window_state(self, widget, event):
        try:
            size = self.get_size()
            position = self.get_position()
            is_maximized = self.is_maximized()

            state = {
                "width": size[0],
                "height": size[1],
                "x": position[0],
                "y": position[1],
                "is_maximized": is_maximized
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f)
            
            logging.info("Estado de janela salvo.")

        except Exception as error:
            logging.warning(f"Erro ao salvar estado: {error}")

        return False

    def load_window_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                self.resize(state.get("width", 1000), state.get("height", 700))

                if state.get("is_maximized", False):
                    self.maximize()
                else:
                    self.move(state.get("x", 0), state.get("y", 0))

                logging.info("Estado de janela restaurado com sucesso.")
                return True
        except Exception as error:
            logging.warning(f"Não foi possível restaurar o estado da janela: {error}")
        return False

    def _on_permission_request(self, webview, request):
        logging.info("Permissão de dispositivo solicitada. Acesso concedido.")
        request.allow()
        return True

    def _on_decide_policy(self, webview, decision, decision_type):
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            navigation_action = decision.get_navigation_action()
            request = navigation_action.get_request()
            uri = request.get_uri()
            
            if uri and "whatsapp.com" not in uri and "javascript:" not in uri:
                try:
                    Gtk.show_uri_on_window(self, uri, Gtk.get_current_event_time())
                    decision.ignore()
                    logging.info(f"Link externo aberto no navegador: {uri}")
                    return True
                except Exception as error:
                    logging.warning(f"Falha ao abrir link externo: {error}")
        
        return False

    def _on_create_web_view(self, webview, navigation_action):
        request = navigation_action.get_request()
        uri = request.get_uri()
        
        if uri:
            try:
                Gtk.show_uri_on_window(self, uri, Gtk.get_current_event_time())
                logging.info(f"Popup/nova janela aberta no navegador: {uri}")
            except Exception as error:
                logging.warning(f"Falha ao abrir popup no navegador: {error}")
        
        return None

if __name__ == "__main__":
    
    GLib.set_prgname("whatsapp")
    
    try:
        app = ClientWindow()
        app.connect("destroy", Gtk.main_quit)
        app.show_all()
        Gtk.main()
    except KeyboardInterrupt:
        # Permite fechar via Terminal com Ctrl+C sem exibir erro.
        logging.info("Aplicação interrompida pelo usuário")
    except Exception as error:
        # Loga qualquer erro não tratado que derrube a aplicação.
        logging.critical("A aplicação caiu inesperadamente", exc_info=True)
