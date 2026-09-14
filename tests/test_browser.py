"""Testes da allowlist e do leitor somente leitura (modo teste simulado)."""
import pytest

from autoexpand.browser.allowed import (SiteNaoAutorizado, UrlInvalida,
                                        autorizar_dominio, remover_dominio,
                                        validar_url, verificar_autorizada)
from autoexpand.browser.reader import PedidoLeitura, ErroLeitura, ler_pagina_autorizada
from autoexpand.config import carregar_config, salvar_config


@pytest.fixture(autouse=True)
def limpar_allowlist():
    cfg = carregar_config()
    cfg.dominio_autorizados = []
    cfg.modo = "teste"
    salvar_config(cfg)
    yield


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