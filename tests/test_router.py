"""Testes do roteador econômico (regras primeiro, cache, fallback)."""
import pytest

from autoexpand.economy import router


@pytest.fixture(autouse=True)
def limpar_cache():
    router._cache.clear()
    if hasattr(router, "_CACHE_ARQUIVO") and router._CACHE_ARQUIVO.exists():
        router._CACHE_ARQUIVO.unlink()
    yield
    router._cache.clear()


def test_regra_primeiro_sem_llm():
    chamadas = {"regra": 0, "barato": 0, "avancado": 0}
    def regra(pedido):
        chamadas["regra"] += 1
        return {"deterministico": True} if "preco" in pedido else None
    def barato(pedido):
        chamadas["barato"] += 1
        return {"llm": True}
    def avancado(pedido):
        chamadas["avancado"] += 1
        return {"llm": True}
    r = router.rotear("consulte o preco aqui",
                      funcao_regra=regra, funcao_llm_barato=barato,
                      funcao_llm_avancado=avancado)
    assert r["fonte"] == "regras"
    assert chamadas["barato"] == 0 and chamadas["avancado"] == 0


def test_cache_reutiliza():
    chamadas = {"regra": 0}
    def regra(pedido):
        chamadas["regra"] += 1
        return {"v": 1}
    r1 = router.rotear("pedido fixo", funcao_regra=regra)
    r2 = router.rotear("pedido fixo", funcao_regra=regra)
    assert r1["fonte"] == "regras"
    assert r2["fonte"] == "cache"
    assert chamadas["regra"] == 1


def test_sem_llm_retorna_nao_resolvido():
    r = router.rotear("algo sem regra", funcao_regra=lambda p: None)
    assert r["fonte"] == "nao_resolvido"