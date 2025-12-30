#!/usr/bin/env python3
"""
Python WhatsApp GTK
-------------------
Um wrapper nativo e leve para WhatsApp Web utilizando WebKit2 e GTK3.
Foco em privacidade (sandbox), performance e integração com o sistema Linux.

Autor: Lourival Dantas
Licença: GPLv3
"""

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
    
    # Se der erro ou se a lista vier vazia, apenas reotna o fallback.
    return fallback_ua

class ClientWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="WhatsApp")
        self.set_default_size(1000, 700)
        
        # Define caminhos absolutos para garantir execução de qualquer lugar.
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wtp_data")
        log_file = os.path.join(base_path, "application.log")

        # Tenta criar a pasta de dados, wtp_data, antes de tudo.
        # Se falhar (ex: permissão negada), encerra o app para evitar crashs silenciosos.
        try:
            os.makedirs(base_path, exist_ok=True)
        except OSError as error:
            sys.stderr.write(f"CRITICAL: Falha ao criar diretório de dados: {error}\n")
            sys.exit(1)

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
                base_data_directory = base_path,
                base_cache_directory = base_path
            )

            context = WebKit2.WebContext.new_with_website_data_manager(data_manager)

            context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)

            self.webview = WebKit2.WebView.new_with_context(context)

            self.webview.connect("decide-policy", self._on_decide_policy)
            self.webview.connect("create", self._on_create_web_view)

            # Aplica o User Agent "falso" para passar pelo filtro do WhatsApp.
            settings = self.webview.get_settings()

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