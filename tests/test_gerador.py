"""Testes da autoexpansão supervisionada por scripts (gerador de módulos)."""
import pytest

from autoexpand.orchestrator.gerador import gerar_modulo


@pytest.fixture(autouse=True)
def isola_conhecimento():
    from autoexpand.config import PASTA_PLUGINS
    from autoexpand.core.persistence import executar
    # não apaga plugins reais: usa nomes de teste bem específicos
    executar("DELETE FROM aprovacoes WHERE modulo LIKE 'teste_%'")
    executar("DELETE FROM modulos WHERE nome LIKE 'teste_%'")
    yield


def test_gerar_modulo_com_nome_e_runtime():
    r = gerar_modulo("teste", nome="teste_dobrar", runtime="python",
                     codigo_extra='return {"dobro": entrada.get("n", 0) * 2}')
    assert r["ok"] is True
    assert r["nome"] == "teste_dobrar"
    assert r["teste"] is True
    assert r["aprovacao_pendente"] is True


def test_gerar_modulo_sem_codigo_extra_passa_sandbox():
    r = gerar_modulo("qualquer", nome="teste_vazio", runtime="python")
    assert r["ok"] is True
    assert r["teste"] in (True, "não testado")


def test_gerar_modulo_runtime_invalido():
    r = gerar_modulo("x", nome="teste_runtime", runtime="ruby")
    assert r["ok"] is False
    assert "runtime" in r.get("erro", "").lower()


def test_base_python_genera_codigo_valido():
    from autoexpand.orchestrator import gerador
    corpo = gerador._corpo("rascunho", "meumod", "python")
    assert "def executar" in corpo
    assert "return" in corpo