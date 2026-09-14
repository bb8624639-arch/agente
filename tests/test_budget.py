"""Testes de orçamento (modo econômico) e bloqueios por limite."""
import pytest

from autoexpand.core import budget
from autoexpand.core.persistence import executar


@pytest.fixture(autouse=True)
def limpar_consumo():
    executar("DELETE FROM consumo")
    budget.encerrar_tarefa()
    budget.iniciar_tarefa()
    yield
    budget.encerrar_tarefa()


def test_custo_por_tarefa_bloqueia():
    budget.registrar_uso(custo_r=2.0)  # atinge teto da tarefa (R$ 2)
    with pytest.raises(budget.LimiteExcedido):
        budget.verificar_limites()


def test_chamadas_ia_por_tarefa_bloqueia():
    budget.registrar_uso(chamadas_ia=10)
    with pytest.raises(budget.LimiteExcedido):
        budget.verificar_limites()


def test_custo_diario_bloqueia():
    budget.registrar_uso(custo_r=5.0)
    with pytest.raises(budget.LimiteExcedido):
        budget.verificar_limites()


def test_custo_mensal_bloqueia():
    budget.registrar_uso(custo_r=20.0)
    with pytest.raises(budget.LimiteExcedido):
        budget.verificar_limites()


def test_consumo_consolidado_limpo():
    consolidado = budget.consumo_consolidado()
    assert consolidado["tarefa"]["custo_r"] == 0.0
    assert consolidado["tarefa"]["chamadas_ia"] == 0
    assert consolidado["dia"]["custo_r"] == 0.0