"""Testes da allowlist e do leitor somente leitura (modo teste simulado)."""
import pytest

from autoexpand.browser.allowed import (SiteNaoAutorizado, UrlInvalida,
                                        acesso_livre, autorizar_dominio,
                                        definir_acesso_livre, remover_dominio,
                                        validar_url, verificar_autorizada)
from autoexpand.browser.reader import PedidoLeitura, ErroLeitura, ler_pagina_autorizada
from autoexpand.config import carregar_config, salvar_config


@pytest.fixture(autouse=True)
def limpar_allowlist():
    cfg = carregar_config()
    cfg.dominio_autorizados = []
    cfg.modo = "teste"
    cfg.acesso_livre_sites = False
    salvar_config(cfg)
    yield
    cfg = carregar_config()
    cfg.acesso_livre_sites = False
    salvar_config(cfg)


def test_url_invalida_rejeitada():
    with pytest.raises(UrlInvalida):
        validar_url("http://nao-https.com")
    with pytest.raises(UrlInvalida):
        validar_url("https://usuario:senha@exemplo.com")
    with pytest.raises(UrlInvalida):
        validar_url("https://192.168.0.1/x")


def test_site_nao_autorizado_bloqueia():
    verificar_autorizada = __import__("autoexpand.browser.allowed",
                                      fromlist=["verificar_autorizada"]).verificar_autorizada
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("https://nao-autorizado.com")


def test_autorizar_subdominio():
    autorizar_dominio("exemplo.com")
    verificar_autorizada("https://api.exemplo.com/v1")  # subdomínio cobre
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("https://outro.org")


def test_remover_dominio():
    autorizar_dominio("exemplo.com")
    remover_dominio("exemplo.com")
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("https://exemplo.com")


def test_leitura_modo_teste_simulado():
    autorizar_dominio("httpbin.org")
    r = ler_pagina_autorizada(PedidoLeitura(url="https://httpbin.org/anything"))
    assert r.get("simulado") is True
    assert r.get("aviso")


def test_leitura_max_paginas_invalido():
    autorizar_dominio("httpbin.org")
    with pytest.raises(ErroLeitura):
        ler_pagina_autorizada(PedidoLeitura(url="https://httpbin.org/anything", max_paginas=99))


# ---- Modo de acesso livre (ignore allowlist, mantém validação de segurança) ----

def test_acesso_livre_desativado_bloqueia_fora_da_allowlist():
    definir_acesso_livre(False)
    assert acesso_livre() is False
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("https://qualquer-site.org/x")


def test_acesso_livre_ativa_libera_qualquer_https():
    definir_acesso_livre(True)
    assert acesso_livre() is True
    # fora da allowlist agora passa
    verificar_autorizada("https://qualquer-site.com/abc")
    # mas a validação de segurança permanece
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("http://nao-https.com")
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("https://192.168.0.1/x")
    definir_acesso_livre(False)


def test_acesso_livre_off_volta_a_bloquear():
    definir_acesso_livre(True)
    definir_acesso_livre(False)
    with pytest.raises(SiteNaoAutorizado):
        verificar_autorizada("https://qualquer-site.org/y")


# ---- Dark web (.onion via Tor) ----

def test_onion_so_com_proxy_tor(monkeypatch):
    definir_acesso_livre(True)
    from autoexpand.browser.allowed import eh_onion
    assert eh_onion("abcdef.onion")
    assert not eh_onion("exemplo.com")
    # sem proxy Tor, o reader recusa .onion
    monkeypatch.delenv("AE_TOR_PROXY", raising=False)
    pedido = PedidoLeitura(url="http://aabbccddeeff.onion/")
    with pytest.raises(ErroLeitura, match="proxy Tor"):
        ler_pagina_autorizada(pedido)
    # com proxy Tor configurado, o simulado passa (não faz rede em modo teste)
    monkeypatch.setenv("AE_TOR_PROXY", "socks5h://127.0.0.1:9050")
    r = ler_pagina_autorizada(PedidoLeitura(url="http://aabbccddeeff.onion/"))
    assert r.get("simulado") is True
    definir_acesso_livre(False)


def test_validar_url_onion():
    from autoexpand.browser.allowed import validar_url
    # http só aceito para .onion
    assert validar_url("http://aabbccddeeff.something.onion/") == "http://aabbccddeeff.something.onion/"
    # .onion com https também ok
    assert validar_url("https://aabbccddeeff.onion/x").startswith("https://")
    # https continua obrigatório para domínio normal
    with pytest.raises(UrlInvalida):
        validar_url("http://nao-onion.com")