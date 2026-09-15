"""Testes do modo conversa (ideologia, 7 portais) e do autosave."""
from pathlib import Path

import pytest

from autoexpand.core import conversa
from autoexpand.core import knowledge


@pytest.fixture(autouse=True)
def isola():
    from autoexpand.config import carregar_config, salvar_config
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    cfg = carregar_config()
    cfg.modo = "teste"
    salvar_config(cfg)
    yield
    # limpa o export de memória gerado por testes
    artefato = Path("docs/agente-memoria.md")
    if artefato.exists():
        artefato.unlink()


def test_ideologia_tem_principios():
    texto = conversa.ideologia()
    assert "Autonomia" in texto and "supervisão" in texto
    assert "Custo consciente" in texto


def test_conversa_saudacao():
    r = conversa.conversar("oi, tudo bem?")
    assert "Estou aqui" in r or "Olá" in r


def test_conversa_agradecimento():
    r = conversa.conversar("obrigado!")
    assert r


def test_conversa_pergunta_existencial():
    r = conversa.conversar("qual é o propósito da sua existência?")
    assert "Autonomia" in r


def test_conversa_sem_base_e_honesta():
    r = conversa.conversar("quanto custa um foguete privado?")
    assert "Ainda não tenho" in r


def test_conversa_usa_conhecimento_aprovado():
    id_c = knowledge.registrar("vendas", "estratégia de vendas é abordar por valor",
                               origem="usuario")
    knowledge.decidir(id_c, True, por="teste")
    r = conversa.conversar("fale sobre vendas")
    assert any(k["topico"] == "vendas" for k in conversa._fatos_relevantes("fale sobre vendas"))
    assert "estratégia de vendas" in r


def test_portais_estrutura_completa():
    r = conversa.portais("como aumentar vendas sem aumentar gastos")
    assert "Sete Portais" in r or "Portal do Enigma" in r
    for nome in ["1. O Portal do Enigma", "5. O Portal da Escolha",
                 "6. O Portal da Execução", "7. O Portal da Reflexão"]:
        assert nome in r


def test_portais_sem_problema():
    r = conversa.portais("")
    assert "problema" in r


def test_portais_aproveita_conhecimento():
    id_c = knowledge.registrar("vendas", "vendas e gastos são aliados quando há métrica",
                               origem="usuario")
    knowledge.decidir(id_c, True, por="teste")
    r = conversa.portais("como reduzir gastos de vendas?")
    assert "forjado com o conhecimento" in r


def test_git_autosave_desligado():
    from autoexpand.core import git_autosave
    orig = git_autosave.AUTOSAVE_LIGADO
    try:
        git_autosave.AUTOSAVE_LIGADO = False
        r = git_autosave.sincronizar_git("teste")
        assert r["ok"] is False
        assert "desligado" in r["detalhe"]
    finally:
        git_autosave.AUTOSAVE_LIGADO = orig


def test_git_autosave_exporta_memoria():
    from autoexpand.core import git_autosave
    id_c = knowledge.registrar("topico_teste", "conteudo_teste exportavel", origem="usuario")
    knowledge.decidir(id_c, True, por="teste")
    orig = git_autosave.AUTOSAVE_LIGADO
    git_autosave.AUTOSAVE_LIGADO = True
    try:
        caminho = git_autosave.exportar_memoria()
        assert caminho and "agente-memoria.md" in caminho
        conteudo = Path(caminho).read_text(encoding="utf-8")
        assert "topico_teste" in conteudo
    finally:
        git_autosave.AUTOSAVE_LIGADO = orig