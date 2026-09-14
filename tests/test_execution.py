"""Testes do executor seguro: tentativas, anti-loop, bloqueio, emergência."""
import pytest

from autoexpand.core import approvals, execution, journal
from autoexpand.core.execution import (Bloqueado, Tarefa, executar_com_recuperacao,
                                       executar_script)


@pytest.fixture(autouse=True)
def reset():
    from autoexpand.core.persistence import executar
    for tabela in ("execucoes", "diario", "consumo", "aprovacoes"):
        executar(f"DELETE FROM {tabela}")
    yield


def _tarefa(**kwargs) -> Tarefa:
    kwargs.setdefault("objetivo", "teste")
    kwargs.setdefault("acao", "ler")
    kwargs.setdefault("permissoes_necessarias", ["ler_pedidos"])
    return Tarefa(**kwargs)


def test_sandbox_ok():
    t = _tarefa()
    r = executar_script(t, 'saida({"dobro": entrada()["n"]*2})', "python", {"n": 3})
    assert r["ok"] is True and r["resultado"]["dobro"] == 6


def test_tentativas_param_no_maximo_3():
    t = _tarefa()
    contador = {"n": 0}
    def fn(estrategia, tentativa):
        contador["n"] += 1
        return {"ok": False, "erro": "sempre falha"}
    r = executar_com_recuperacao(t, fn)
    assert r["ok"] is False
    assert contador["n"] == 3  # limite de tentativas
    assert t.status == "bloqueada"


def test_nao_inventa_sucesso():
    t = _tarefa()
    def fn(estrategia, tentativa):
        return {"ok": False, "erro": "boom"}
    r = executar_com_recuperacao(t, fn)
    assert "não inventa sucesso" in r["erro"] or r["ok"] is False
    assert "erro" in r


def test_acao_sensivel_sem_aprovacao_bloqueia():
    t = Tarefa(objetivo="x", acao="pagamento")
    with pytest.raises(Bloqueado):
        execution.verificar_pre_voo(t, __import__("autoexpand.config", fromlist=["carregar_config"]).carregar_config())


def test_modo_emergencia_bloqueia():
    from autoexpand.config import carregar_config, salvar_config
    cfg = carregar_config()
    cfg.emergencia = True
    salvar_config(cfg)
    try:
        t = _tarefa()
        with pytest.raises(Bloqueado):
            execution.verificar_pre_voo(t, carregar_config())
    finally:
        cfg.emergencia = False
        salvar_config(cfg)


def test_permissao_negada_bloqueia():
    t = Tarefa(objetivo="x", acao="ler",
               permissoes_necessarias=["sistema"])  # não concedida globalmente
    with pytest.raises(Bloqueado):
        executar_script(t, "pass", "python", {})