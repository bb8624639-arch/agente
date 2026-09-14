"""Testes do registro versionado: publicar nunca sobrescreve estável, rollback."""
import pytest

from autoexpand.core import registry
from autoexpand.core.persistence import consultar_um

MANIFESTO = {
    "nome": "mod_teste", "versao": "1.0.0", "perfil": "rascunho",
    "permissoes": ["ler_pedidos"], "input_schema": {}, "output_schema": {},
}


@pytest.fixture(autouse=True)
def limpar_banco():
    from autoexpand.core.persistence import _conexao, executar
    conexao = _conexao()
    for tabela in ("modulos", "versoes", "execucoes", "aprovacoes", "consumo", "diario"):
        conexao.execute(f"DELETE FROM {tabela}")
    conexao.commit()
    yield


def test_publicar_primeira_versao():
    registry.publicar("mod_teste", MANIFESTO, aprovado=True)
    atual = registry.versao_atual("mod_teste")
    assert atual["versao"] == "1.0.0"
    assert atual["aprovado"] is True


def test_publicar_nao_sobrescreve_estavel():
    registry.publicar("mod_teste", MANIFESTO, aprovado=True)
    v2 = dict(MANIFESTO, versao="1.0.1")
    registry.publicar("mod_teste", v2, aprovado=True)
    # Estável original ainda publicada e presente
    assert registry.modulo_por_versao("mod_teste", "1.0.0")["versao"] == "1.0.0"
    # Atual é a mais alta
    assert registry.versao_atual("mod_teste")["versao"] == "1.0.1"


def test_rollback_restaura_versao_anterior():
    registry.publicar("mod_teste", MANIFESTO, aprovado=True)
    v2 = dict(MANIFESTO, versao="1.0.1")
    registry.publicar("mod_teste", v2, aprovado=True)
    registry.rollback("mod_teste", "1.0.0", motivo="regressão")
    assert registry.versao_atual("mod_teste")["versao"] == "1.0.0"
    # O 1.0.1 ficou inativo (não foi apagado) — histórico preservado
    linha = consultar_um(
        "SELECT status FROM modulos WHERE nome='mod_teste' AND versao='1.0.1'")
    assert linha and linha["status"] == "inativo"
    # Histórico registra a ação de rollback (mais recente primeiro)
    acoes = [h["acao"] for h in registry.historico_versoes("mod_teste")]
    assert acoes[0] == "rollback"


def test_historico_cresce():
    registry.publicar("mod_teste", MANIFESTO, aprovado=True)
    registry.publicar("mod_teste", dict(MANIFESTO, versao="1.0.2"), aprovado=True)
    hist = registry.historico_versoes("mod_teste")
    assert len(hist) == 2
    assert all(h["acao"] == "publicar" for h in hist)


def test_permissao_desconhecida_rejeitada():
    invalido = dict(MANIFESTO, permissoes=["ler_coisa_estranha"])
    from autoexpand.core.plugin import SchemaInvalido
    with pytest.raises(SchemaInvalido):
        registry.registrar_manifesto(invalido)