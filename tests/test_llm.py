"""Testes do adaptador de LLM multi-provedor (sem rede, com mocks)."""
import pytest

from autoexpand.economy import llm


@pytest.fixture(autouse=True)
def limpar_estado(monkeypatch):
    """Isola o estado global do módulo llm entre testes."""
    orig = {k: getattr(llm, k) for k in
            ("BASE_URL", "API_KEY", "MODELO_BARATO", "MODELO_AVANCADO",
             "PROVEDOR_ATUAL", "TEM_LLM")}
    yield
    for k, v in orig.items():
        setattr(llm, k, v)


def test_catalogo_tem_openhands():
    prov = llm.PROVEDORES["openhands"]
    assert prov["tipo"] == "openhands"
    assert prov["base_url"] == "https://app.all-hands.dev"


def test_catalogo_tem_gemini_openai():
    assert llm.PROVEDORES["gemini"]["tipo"] == "openai"
    assert llm.PROVEDORES["openai"]["base_url"] == "https://api.openai.com/v1"


def test_sinonimos_provedor():
    assert llm._normalizar_provedor("All-Hands") == "openhands"
    assert llm._normalizar_provedor("ALL_HANDS") == "openhands"
    assert llm._normalizar_provedor("google") == "gemini"
    assert llm._normalizar_provedor("Ollama") == "local"
    assert llm._normalizar_provedor("gemini") == "gemini"


def test_reconfigurar_aceita_sinonimo_allhands():
    ok = llm.reconfigurar(provider="All-Hands", api_key="chave")
    assert ok is True
    assert llm.PROVEDOR_ATUAL == "openhands"
    assert llm._tipo_atual() == "openhands"


def test_reconfigurar_por_slug_openhands():
    ok = llm.reconfigurar(provider="openhands", api_key="chave_all_hands")
    assert ok is True
    assert llm.BASE_URL == "https://app.all-hands.dev"
    assert llm.API_KEY == "chave_all_hands"
    assert llm.PROVEDOR_ATUAL == "openhands"
    assert llm._tipo_atual() == "openhands"


def test_reconfigurar_por_slug_gemini_preenche_modelos():
    llm.reconfigurar(provider="gemini", api_key="x")
    assert llm.MODELO_BARATO == "gemini-2.0-flash"
    assert llm.BASE_URL == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_reconfigurar_sem_chave_desabilita():
    llm.reconfigurar(provider="gemini", api_key="x")
    assert llm.disponivel() is True
    llm.reconfigurar(api_key="")
    assert llm.disponivel() is False


def test_disponivel_sem_config():
    from autoexpand.economy import llm as m
    reconf = m.reconfigurar(api_key="", base_url="")
    assert reconf is False
    assert m.disponivel() is False


def test_erro_network_vira_resposta_vazia(monkeypatch):
    """Falha de rede não deve quebrar o pipeline; vira resposta vazia + erro."""
    from autoexpand.economy import llm as m
    m.reconfigurar(provider="gemini", api_key="chave")
    assert m.disponivel() is True

    def _boom(prompt, modelo, motivo, temperatura=0.0, max_saida=2000):
        raise ConnectionError("network down")

    monkeypatch.setattr(m, "_chamar_openai", _boom)
    r = m._chamar("teste", m.MODELO_BARATO, "teste de erro")
    assert r.resposta == ""
    assert "erro:" in r.erro


def test_testar_conexao_sem_llm():
    llm.reconfigurar(api_key="", base_url="")
    ok, detalhe = llm.testar_conexao()
    assert ok is False
    assert "nenhuma" in detalhe or "configurada" in detalhe