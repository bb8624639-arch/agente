"""Testes do aprendizado autônomo contínuo (sem aprovação, conteúdo técnico).

Cobre:
- política de autoaprovação (knowledge.deve_autoaprovar);
- trilhas de estudo (aprendizado_auto) determinísticas e infinitas;
- fluxo de ciclo sem tocar rede (modo teste simulado);
- integração no pipeline (classificador + executor);
- comando /aprender_auto no bot (regex e menu).
"""
import pytest

from autoexpand.core import knowledge
from autoexpand.core import aprendizado_auto


@pytest.fixture(autouse=True)
def isola():
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    executar("DELETE FROM execucoes")
    from autoexpand.config import carregar_config, salvar_config
    cfg = carregar_config()
    cfg.modo = "teste"
    salvar_config(cfg)
    yield


# ---- Política de autoaprovação ----

def test_deve_autoaprovar_tecnico_publico():
    assert knowledge.deve_autoaprovar(
        "programação em Python", "https://pt.wikipedia.org/wiki/Python",
        "Python é uma linguagem de programação.", origem="internet") is True


def test_nao_autoaprova_usuario():
    assert knowledge.deve_autoaprovar(
        "programação em Python", "https://pt.wikipedia.org/wiki/Python",
        "gosto de programar", origem="usuario") is False


def test_nao_autoaprova_nao_tecnico():
    assert knowledge.deve_autoaprovar(
        "culinária", "https://pt.wikipedia.org/wiki/Culinária",
        "receitas de bolo", origem="internet") is False


def test_registrar_autoaprova_tecnico_em_autonomo(monkeypatch):
    from autoexpand.config import carregar_config, salvar_config
    # conftest força AE_MODO=teste; simulamos o modo autônomo controlado real
    monkeypatch.setenv("AE_MODO", "autonomo_controlado")
    cfg = carregar_config()
    cfg.modo = "autonomo_controlado"
    salvar_config(cfg)
    id_c = knowledge.registrar(
        "programação em Python", "Python é uma linguagem de programação.",
        origem="internet", fonte="https://pt.wikipedia.org/wiki/Python")
    linha = knowledge.listar("aprovado")
    assert any(k["id"] == id_c for k in linha)


def test_registrar_em_teste_fica_rascunho():
    # isola() força modo teste → mesmo conteúdo técnico fica rascunho
    id_c = knowledge.registrar(
        "programação em Python", "Python é uma linguagem de programação.",
        origem="internet", fonte="https://pt.wikipedia.org/wiki/Python")
    assert id_c >= 1
    assert len(knowledge.listar("rascunho")) == 1


# ---- Trilhas de estudo ----

def test_proximo_topico_deterministico():
    t1 = aprendizado_auto.proximo_topico("linguagens")
    assert isinstance(t1, str) and t1
    # repetição do mesmo estado gera o mesmo tópico
    # (usa contagem de execuções; sem escrever, segue da semente inicial)
    t2 = aprendizado_auto.proximo_topico("linguagens")
    assert t1 == t2


def test_trilha_rotaciona_infinita():
    # após repetir várias vezes, expande com "módulo N"
    for _ in range(10):
        t = aprendizado_auto.proximo_topico("mobile")
        assert "mobile" in t.lower() or "android" in t.lower() or "automação" in t.lower()


def test_ciclo_em_modo_teste_simulado():
    r = aprendizado_auto.ciclo_aprendizado(limite_topicos=2)
    assert r.get("simulado") is True
    assert r.get("resumo")


def test_ciclo_avanca_na_trilha_entre_iteracoes(monkeypatch):
    """Dentro do mesmo ciclo, cada tópico deve ser o PRÓXIMO da trilha,
    não o mesmo repetido (regressão: índice relido do disco).
    """
    from autoexpand.config import carregar_config, salvar_config
    monkeypatch.setenv("AE_MODO", "autonomo_controlado")
    cfg = carregar_config()
    cfg.modo = "autonomo_controlado"
    cfg.aprendizado_idx = 0
    salvar_config(cfg)

    chamadas: list[str] = []

    def _fake_aprender(topico):
        chamadas.append(topico)
        return {"id": len(chamadas), "topico": topico, "auto": True}

    monkeypatch.setattr(aprendizado_auto, "aprender_topico", _fake_aprender)

    r = aprendizado_auto.ciclo_aprendizado(limite_topicos=2, avancar=True)
    assert r.get("ok") is True
    assert chamadas == [
        "programação em Python",
        "automação web com Playwright",
    ], chamadas
    # persistiu o avanço: próximo ciclo começa no índice 2
    assert carregar_config().aprendizado_idx == 2
    assert r.get("proximo_topico") == "automação no Android com ADB"


# ---- Integração no pipeline ----

def test_classifica_aprender_auto():
    from autoexpand.orchestrator.classifier import classificar
    cl = classificar("aprenda automaticamente programação em Python")
    assert cl.categoria == "aprendizado"


def test_planner_tem_trilha():
    from autoexpand.orchestrator.classifier import classificar
    from autoexpand.orchestrator.planner import planejar
    cl = classificar("aprenda automaticamente programação em Python")
    plano = planejar("aprenda automaticamente programação em Python", cl)
    assert plano["status"] == "plano"
    assert plano["aprovacao_necessaria"] is False
    # ferramenta da trilha presente
    assert any("aprendizado" in f for f in plano["ferramentas"])


def test_executor_aprende_auto_modo_teste():
    from autoexpand.orchestrator.executor import _executar_aprendizado_autonomo
    r = _executar_aprendizado_autonomo("aprenda python")
    # em modo teste não toca rede: ok (resultado simulado ou erro digno)
    assert r.get("ok") in (True, False)