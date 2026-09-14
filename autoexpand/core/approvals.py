"""Fila e política de aprovações.

Norma (item 6 do usuário): mesmo em modo autônomo, exigem aprovação humana ou
permanecem bloqueadas: pagamentos, reembolsos, Pix, cartão, contratação,
alteração de credenciais, exclusão definitiva, mensagens em massa, publicação
de conteúdo, alteração de preços, contato comercial, contas de terceiros,
qualquer ação fora da allowlist, alterar regras de segurança, aumento de
orçamento e execução de código não testado em produção.

`requer_aprovacao(acao, ...)` é determinística e roda SEMPRE antes de executar.
Se não houver humano disponível, a ação permanece bloqueada e o orquestrador
segue com as demais tarefas independentes.
"""

from __future__ import annotations

import time
import uuid

from ..config import SEMPRE_APROVAR
from .persistence import consultar, consultar_um, executar

CLASSIFICACAO_ACAO = {
    "pagamento": "pagamentos", "pix": "pix", "reembolso": "reembolsos",
    "cartao": "cartao", "contratar": "contratacao_servicos",
    "credencial": "credenciais", "excluir_dados": "exclusao_definitiva",
    "exclusao_definitiva": "exclusao_definitiva",
    "enviar_em_massa": "mensagens_em_massa", "publicar_conteudo": "publicacao_conteudo",
    "alterar_preco": "alteracao_precos", "alteracao_preco": "alteracao_precos",
    "contato_comercial": "contato_comercial", "contatar_cliente": "contato_comercial",
    "conta_terceiros": "contas_terceiros", "fora_allowlist": "fora_da_allowlist",
    "alterar_regras": "alterar_regras_seguranca", "aumentar_orcamento": "aumento_orcamento",
    "publicar_modulo": "publicacao_modulo",
    "deploy_producao": "deploy_producao",
    "enviar_mensagem": "envio_mensagem",
}


def acao_de(classe: str) -> str:
    """Mapeia nome interno da ação para a chave usada na política de aprovação."""
    return CLASSIFICACAO_ACAO.get(classe, classe)


def exige_aprovacao_sempre(classe: str) -> bool:
    """Determinístico: a ação pertence ao conjunto sempre-humano dependente de
    efeito colateral irreversível/custo (regra 6 do usuário)."""
    base = acao_de(classe)
    return (base in SEMPRE_APROVAR
            or base in ("publicacao_modulo", "deploy_producao", "envio_mensagem"))


def requer_aprovacao(pedido: dict, *, modo: str) -> bool:
    """Decisão final: a ação do pedido exige aprovação humana neste modo?"""
    if modo == "emergencia":
        return True
    acao = pedido.get("acao", "")
    classe = acao_de(pedido.get("classe", acao))
    sensivel = exige_aprovacao_sempre(acao) or classe in SEMPRE_APROVAR
    if sensivel:
        return True
    if modo in ("teste", "autonomo_controlado") and pedido.get("efeito_externo"):
        return True
    return False


def criar_aprovacao(acao: str, *, modulo: str = "", contexto: dict | None = None) -> str:
    """Cria registro de aprovação pendente e devolve o id."""
    ap_id = uuid.uuid4().hex[:16]
    executar(
        "INSERT INTO aprovacoes (id, acao, modulo, contexto, status, criado_em) "
        "VALUES (?,?,?,?, 'pendente', ?)",
        (ap_id, acao, modulo,
         __import__("json").dumps(contexto or {}, ensure_ascii=False), time.time()))
    return ap_id


def decidir(ap_id: str, aprovado: bool, *, por: str = "humano") -> dict | None:
    """Registra decisão humana. Devolve o registro atualizado ou None se não existe."""
    linha = consultar_um("SELECT * FROM aprovacoes WHERE id=?", (ap_id,))
    if not linha:
        return None
    if linha["status"] != "pendente":
        return dict(linha)
    executar("UPDATE aprovacoes SET status=?, decidido_por=?, decidido_em=? WHERE id=?",
             ("aprovado" if aprovado else "recusado", por, time.time(), ap_id))
    return consultar_um("SELECT * FROM aprovacoes WHERE id=?", (ap_id,))


def status_aprovacao(ap_id: str) -> str:
    linha = consultar_um("SELECT status FROM aprovacoes WHERE id=?", (ap_id,))
    return linha["status"] if linha else "desconhecido"


def pendentes() -> list[dict]:
    return consultar("SELECT * FROM aprovacoes WHERE status='pendente' ORDER BY criado_em")


def bloqueada_por_falta_de_aprovacao(classe: str) -> bool:
    """Item 6: se não houver aprovação, a ação sensível permanece bloqueada."""
    return exige_aprovacao_sempre(classe)