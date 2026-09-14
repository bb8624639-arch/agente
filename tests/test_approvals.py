"""Testes da política de aprovação humana."""
import pytest

from autoexpand.core import approvals
from autoexpand.core.persistence import executar


@pytest.fixture(autouse=True)
def limpar_aprovacoes():
    executar("DELETE FROM aprovacoes")
    yield


def test_acoes_sensiveis_exigem_aprovacao():
    for acao in ("pagamento", "pix", "reembolso", "cartao",
                 "alteracao_preco", "exclusao_definitiva", "enviar_mensagem",
                 "contatar_cliente", "deploy_producao", "publicar_modulo"):
        assert approvals.exige_aprovacao_sempre(acao), f"deveria exigir: {acao}"


def test_acoes_leitura_nao_exigem():
    assert not approvals.exige_aprovacao_sempre("ler")
    assert not approvals.exige_aprovacao_sempre("ler_site")
    assert not approvals.exige_aprovacao_sempre("diagnosticar")


def test_criar_e_decidir_aprovacao():
    ap = approvals.criar_aprovacao("enviar_mensagem", modulo="x")
    assert approvals.status_aprovacao(ap) == "pendente"
    approvals.decidir(ap, True, por="ana")
    assert approvals.status_aprovacao(ap) == "aprovado"


def test_recusar_aprovacao():
    ap = approvals.criar_aprovacao("pagamento", modulo="x")
    approvals.decidir(ap, False, por="ana")
    assert approvals.status_aprovacao(ap) == "recusado"


def test_acoes_nao_aprovadas_permanecem_bloqueadas():
    # Sem decisão → bloqueado por falta de aprovação
    assert approvals.bloqueada_por_falta_de_aprovacao("pagamento")
    assert not approvals.bloqueada_por_falta_de_aprovacao("ler")