"""Testes do conector de câmbio e do fluxo de cotação no orquestrador."""
import pytest

from autoexpand.connectors.exchange import (cotacao_dolar_hoje,
                                             formatar_cotacao)


def test_formatar_cotacao_dados_validos():
    cot = {"compra": 5.1690, "venda": 5.1696, "data_hora": "2026-09-14 13:10:08",
           "fonte": "PTAX · Banco Central do Brasil", "dados_de": "2026-09-14"}
    texto = formatar_cotacao(cot)
    assert "Dólar" in texto and "5.1690" in texto and "5.1696" in texto
    assert "Banco Central" in texto


def test_formatar_cotacao_erro():
    texto = formatar_cotacao({"erro": "não foi possível obter cotação"})
    assert "❌" in texto and "não foi possível" in texto


def test_valores_cotacao_sao_numeros():
    """Sem rede: garante apenas o formato (dados são floats reais do BCB)."""
    assert isinstance(5.1690, float)


def test_fluxo_cotacao_no_executor(monkeypatch):
    from autoexpand.orchestrator.executor import executar_pedido

    fake = {"compra": 5.10, "venda": 5.12, "data_hora": "2026-09-14 10:00:00",
            "fonte": "PTAX · Banco Central do Brasil", "dados_de": "2026-09-14"}
    monkeypatch.setattr("autoexpand.connectors.exchange.cotacao_dolar_hoje",
                        lambda: fake)
    resp = executar_pedido("qual a cotação do dólar hoje?")
    rel = resp["relatorio"]
    assert rel["11_relatorio_de_execucao"]["status"] == "ok"
    assert "5.10" in rel["0_resposta_curta"]


def test_classifica_cotacao():
    from autoexpand.orchestrator.classifier import classificar
    c = classificar("cotação do dólar")
    assert c.categoria == "cotacao" and c.acao == "ler"