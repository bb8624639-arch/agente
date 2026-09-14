"""Testes de ponta a ponta do orquestrador (modo teste)."""
import pytest

from autoexpand.orchestrator.executor import executar_pedido
from autoexpand.config import carregar_config, salvar_config
from autoexpand.browser.allowed import autorizar_dominio, remover_dominio


@pytest.fixture(autouse=True)
def ambiente_teste():
    from autoexpand.core.persistence import executar
    for tabela in ("execucoes", "diario", "consumo", "aprovacoes"):
        executar(f"DELETE FROM {tabela}")
    cfg = carregar_config()
    cfg.modo = "teste"
    cfg.emergencia = False
    salvar_config(cfg)
    yield
    cfg.emergencia = False
    salvar_config(cfg)


def test_pedido_leitura_modo_teste():
    autorizar_dominio("httpbin.org")
    resposta = executar_pedido(
        "consulte o preço em https://httpbin.org/anything e retorne o campo args")
    assert resposta["status"] == "ok"
    rel = resposta["relatorio"]
    assert rel["1_objetivo_entendido"]
    assert rel["11_relatorio_de_execucao"]["status"] == "ok"
    assert resposta.get("handoff")


def test_pedido_desconhecido_pede_desambiguacao():
    resposta = executar_pedido("aloha festa")
    assert resposta["status"] == "desconhecida"


def test_acao_sensivel_cria_aprovacao():
    resposta = executar_pedido(
        "envie uma mensagem para o cliente pelo whatsapp")
    assert resposta["status"] == "aprovacao"
    acoes = resposta["relatorio"]["8_acoes_que_precisam_aprovacao"]
    assert acoes and acoes[0]["acao"] == "enviar_mensagem"


def test_site_nao_autorizado_bloqueado():
    remover_dominio("httpbin.org")
    resposta = executar_pedido(
        "consulte o preço em https://nao-autorizado.com e retorne o campo")
    assert resposta["status"] in ("falha", "bloqueada")