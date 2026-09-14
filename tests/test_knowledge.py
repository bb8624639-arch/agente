"""Testes da memória de aprendizado (conhecimento) e do fluxo de supervisão."""
import pytest

from autoexpand.core import knowledge


@pytest.fixture(autouse=True)
def isola():
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    yield


def test_registrar_e_listar_aprovado():
    id_c = knowledge.registrar("preferência", "cliente prefere WhatsApp", origem="usuario")
    assert id_c >= 1
    aprovados = knowledge.listar("aprovado")
    rascunhos = knowledge.listar("rascunho")
    assert len(rascunhos) == 1 and len(aprovados) == 0


def test_decidir_aprova():
    id_c = knowledge.registrar("técnica", "usar cache em leituras", origem="usuario")
    r = knowledge.decidir(id_c, True, por="teste")
    assert r["status"] == "aprovado"
    aprovados = knowledge.listar("aprovado")
    assert len(aprovados) == 1 and aprovados[0]["id"] == id_c


def test_aprender_da_internet_cria_rascunho(monkeypatch):
    # mock da fonte externa para teste sem rede
    def fake(nome):
        return {"topico": "XPTO", "conteudo": "resumo",
                "fonte": "http://fake/xpto", "origem": "internet"}
    monkeypatch.setattr(knowledge, "buscar_completo", fake)
    r = knowledge.aprender_e_registrar("qualquer")
    assert "id" in r
    assert r["topico"] == "XPTO"
    # continua rascunho — precisa supervisão
    rascunhos = knowledge.listar("rascunho")
    assert len(rascunhos) == 1 and rascunhos[0]["origem"] == "internet"


def test_registrar_sem_conteudo_erro():
    with pytest.raises(ValueError):
        knowledge.registrar("", "")