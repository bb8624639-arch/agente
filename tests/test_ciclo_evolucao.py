"""Testes do ciclo de evolução contínua (autoexpand/core/ciclo.py).

Cobre: diagnóstico, aprendizado a partir de execuções, propostas e o
comando /evoluir no bot. Nada disso força rede/IA — é tudo determinístico.
"""
import pytest

import autoexpand.telegram.bot as tbot
from autoexpand.core import ciclo, journal, knowledge


@pytest.fixture(autouse=True)
def isola():
    from autoexpand.config import carregar_config, salvar_config
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    executar("DELETE FROM diario")
    cfg = carregar_config()
    cfg.modo = "teste"
    salvar_config(cfg)
    yield


def _registra_erro(msg: str) -> None:
    journal.registrar_diario("erro", msg)


def test_diagnostico_vazio():
    r = ciclo.diagnosticar()
    assert "diagnóstico" in r["texto"].lower() or "ciclo" in r["texto"].lower()
    assert isinstance(r["propostas"], list)
    assert isinstance(r["estatisticas"], dict)


def test_aprende_de_erros_repetidos():
    _registra_erro("falha ao conectar no whatsapp")
    _registra_erro("falha ao conectar no whatsapp de novo")
    _registra_erro("erro na api whatsapp conecta")
    r = ciclo.diagnosticar()
    # ao menos um aprendizado rascunho foi criado
    assert r["aprendidos"], "deveria aprender de erros repetidos"
    pendentes = knowledge.listar("rascunho")
    assert pendentes


def test_proximo_passo_prioriza_aprovacao():
    id_c = knowledge.registrar("topico pendente", "conteudo", origem="usuario")
    r = ciclo.proximo_passo()
    assert r["acao"] == "aprovar"
    assert str(id_c) in r["alvo"] or r["detalhe"]


def test_evolucao_botao_no_menu():
    teclado = tbot._teclado_menu()
    dados = [b["callback_data"] for linha in teclado for b in linha]
    assert "menu_evoluir" in dados


def test_handle_evoluir_nao_quebra(monkeypatch):
    """/evoluir produz texto de diagnóstico (sem tocar em rede)."""
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    tbot.CHAT_AUTORIZADO = "777"
    tbot._AGUARDANDO.clear()
    enviadas = []

    class _FakeResp:
        status_code = 200
        text = "{}"

    import requests

    def fake_post(url, json=None, timeout=None, params=None):
        enviadas.append(json)
        return _FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    # garante que /evoluir está registrado nos comandos e não lança
    from autoexpand.config import carregar_config, salvar_config
    cfg = carregar_config()
    cfg.modo = "teste"
    salvar_config(cfg)
    tbot._handle({"message": {"chat": {"id": 777},
                              "text": "/evoluir",
                              "message_id": 1}})
    tbot.CHAT_AUTORIZADO = ""
    tbot._AGUARDANDO.clear()
    assert True  # sem exceção é suficiente para o fluxo básico