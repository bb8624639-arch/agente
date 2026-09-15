"""Testes das novas capacidades: pesquisa web, memória/pensar, contexto colado."""
import pytest

from autoexpand.core import knowledge
from autoexpand.browser import search


@pytest.fixture(autouse=True)
def isola():
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    from autoexpand.config import carregar_config, salvar_config
    cfg = carregar_config()
    cfg.modo = "teste"
    salvar_config(cfg)
    yield


def test_buscar_web_modo_teste_simulado():
    # modo teste → busca simulada, sem rede
    r = search.buscar_web("inteligencia artificial")
    assert r.get("simulado") is True
    assert "resultados" in r


def test_memory_pensar_sem_dados():
    from autoexpand.core.memory import pensar
    r = pensar()
    assert "texto_resposta" in r
    assert r["texto_resposta"].strip()


def test_memory_pensar_com_conhecimento_aprovado():
    from autoexpand.core import memory, knowledge
    id_c = knowledge.registrar("marketing", "estratégia de funil é essencial",
                               origem="usuario")
    knowledge.decidir(id_c, True, por="teste")
    r = memory.pensar()
    assert any("marketing" in f["topico"] for f in r["fatos"])


def test_contexto_importa_rascunho():
    from autoexpand.orchestrator.executor import _executar_contexto
    texto_longo = (
        "Este é um documento de treinamento longo sobre automação comercial.\n"
        "O MVP-2 prevê autoexpansão supervisionada com scripts.\n"
        "O agente deve aprender com o contexto colado no Telegram.\n"
    ) * 5
    r = _executar_contexto(texto_longo)
    assert r["ok"] is True
    assert r["resultado"]["id"] >= 1
    # é rascunho aguardando aprovação
    assert len(knowledge.listar("rascunho")) == 1


def test_contexto_texto_curto_rejeitado():
    from autoexpand.orchestrator.executor import _executar_contexto
    r = _executar_contexto("texto pequeno")
    assert r["ok"] is False