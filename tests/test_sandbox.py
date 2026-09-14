"""Testes do sandbox: execução, timeout, memória, kill de loop."""
import pytest

from autoexpand.core import sandbox_runner


def test_python_ok():
    r = sandbox_runner.executar(
        'saida({"dobro": entrada()["n"]*2})', "python", {"n": 21}, timeout=5, memoria_mb=64)
    assert r["ok"] is True and r["resultado"]["dobro"] == 42


def test_javascript_ok():
    r = sandbox_runner.executar(
        "saida({soma: entrada().a + entrada().b})", "javascript", {"a": 2, "b": 3},
        timeout=5, memoria_mb=64)
    assert r["ok"] is True and r["resultado"]["soma"] == 5


def test_timeout_forcado():
    r = sandbox_runner.executar("import time; time.sleep(30); saida({})", "python", {},
                                timeout=2, memoria_mb=64)
    assert r["ok"] is False
    assert "timeout" in (r.get("erro") or "").lower()


def test_loop_infinito_kill():
    r = sandbox_runner.executar("while True: pass", "python", {}, timeout=2, memoria_mb=64)
    assert r["ok"] is False


def test_erro_excecao_reportado():
    r = sandbox_runner.executar("raise ValueError('boom')", "python", {}, timeout=5, memoria_mb=64)
    assert r["ok"] is False
    assert "boom" in (r.get("erro") or "")