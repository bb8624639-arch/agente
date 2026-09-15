"""Planejador de etapas — templates determinísticos por categoria.

Sem IA por padrão: cada categoria tem um modelo de plano com etapas,
ferramentas, permissões, riscos e pontos de aprovação. Se um pedido é
desconhecido OU ambíguo, devolve a flag `ne_desambiguacao` com perguntas —
nunca inventa plano.
"""

from __future__ import annotations

from ..config import carregar_config
from ..core.registry import versao_atual
from .classifier import (PERGUNTAS_DESAMBIGUACAO, Classificacao, ambiguidade)


def _etapas_leitura() -> list[dict]:
    return [
        {"ordem": 1, "nome": "validar URL autorizada", "ferramenta": "browser/allowed",
         "permissao": "rede", "deterministico": True},
        {"ordem": 2, "nome": "fazer GET e extrair trecho", "ferramenta": "browser/reader",
         "permissao": "ler_api", "deterministico": True},
        {"ordem": 3, "nome": "validar saída contra schema", "ferramenta": "core/validation",
         "permissao": "", "deterministico": True},
    ]


def _etapas_banco() -> list[dict]:
    return [
        {"ordem": 1, "nome": "selecionar módulo de banco (leitura)", "ferramenta": "db/leitor",
         "permissao": "ler_db", "deterministico": True},
        {"ordem": 2, "nome": "rodar consulta parametrizada", "ferramenta": "core/execution",
         "permissao": "ler_db", "deterministico": True},
    ]


def _etapas_mensagens() -> list[dict]:
    return [
        {"ordem": 1, "nome": "identificar destinatário (autorizado)", "ferramenta": "telegram/bot",
         "permissao": "mensagens", "deterministico": True},
        {"ordem": 2, "nome": "OBTER APROVAÇÃO HUMANA", "ferramenta": "core/approvals",
         "permissao": "mensagens", "deterministico": True},
        {"ordem": 3, "nome": "enviar mensagem", "ferramenta": "telegram/bot",
         "permissao": "mensagens", "deterministico": True},
    ]


def _etapas_criar_modulo() -> list[dict]:
    return [
        {"ordem": 1, "nome": "gerar código no sandbox", "ferramenta": "orchestrator/gerador",
         "permissao": "", "deterministico": False},
        {"ordem": 2, "nome": "testar em sandbox", "ferramenta": "core/sandbox_runner",
         "permissao": "", "deterministico": True},
        {"ordem": 3, "nome": "validar manifesto e permissões", "ferramenta": "core/plugin",
         "permissao": "", "deterministico": True},
        {"ordem": 4, "nome": "OBTER APROVAÇÃO p/ publicar", "ferramenta": "core/approvals",
         "permissao": "publicacao_modulo", "deterministico": True},
    ]


def _etapas_erro() -> list[dict]:
    return [
        {"ordem": 1, "nome": "ler journal/execuções recentes", "ferramenta": "core/journal",
         "permissao": "", "deterministico": True},
        {"ordem": 2, "nome": "gerar diagnóstico (regras, sem LLM)", "ferramenta": "orchestrator/planner",
         "permissao": "", "deterministico": True},
        {"ordem": 3, "nome": "se vazio → repassar p/ manutenção/LLM avançado", "ferramenta": "economy/llm",
         "permissao": "", "deterministico": False},
    ]


def _etapas_cotacao() -> list[dict]:
    return [
        {"ordem": 1, "nome": "consultar PTAX do Banco Central (USD/BRL)", "ferramenta": "connectors/exchange",
         "permissao": "ler_api", "deterministico": True},
        {"ordem": 2, "nome": "formatar cotação (compra/venda)", "ferramenta": "connectors/exchange",
         "permissao": "", "deterministico": True},
    ]


def _etapas_pesquisa_livre() -> list[dict]:
    return [
        {"ordem": 1, "nome": "buscar na internet (DuckDuckGo)", "ferramenta": "browser/search",
         "permissao": "rede", "deterministico": True},
        {"ordem": 2, "nome": "abrir paginas permitidas (allowlist)", "ferramenta": "browser/reader",
         "permissao": "rede", "deterministico": True},
        {"ordem": 3, "nome": "registrar aprendizado como rascunho", "ferramenta": "core/knowledge",
         "permissao": "", "deterministico": True},
    ]


def _etapas_aprender_autonomo() -> list[dict]:
    return [
        {"ordem": 1, "nome": "escolher próximo tópico (trilha)", "ferramenta": "core/aprendizado_auto",
         "permissao": "", "deterministico": True},
        {"ordem": 2, "nome": "buscar conteúdo técnico (internet)", "ferramenta": "core/knowledge",
         "permissao": "rede", "deterministico": True},
        {"ordem": 3, "nome": "autoaprovar se técnico/público ou deixar rascunho",
         "ferramenta": "core/knowledge", "permissao": "", "deterministico": True},
    ]


def _etapas_pensar() -> list[dict]:
    return [
        {"ordem": 1, "nome": "sintetizar conhecimento aprovado", "ferramenta": "core/memory",
         "permissao": "", "deterministico": True},
        {"ordem": 2, "nome": "agregar execuções/erros recentes", "ferramenta": "core/journal",
         "permissao": "", "deterministico": True},
        {"ordem": 3, "nome": "gerar sugestões acionáveis", "ferramenta": "core/memory",
         "permissao": "", "deterministico": True},
    ]


def _etapas_contexto() -> list[dict]:
    return [
        {"ordem": 1, "nome": "segmentar texto colado (documento)", "ferramenta": "core/knowledge",
         "permissao": "", "deterministico": True},
        {"ordem": 2, "nome": "classificar partes relevantes", "ferramenta": "orchestrator/classifier",
         "permissao": "", "deterministico": True},
        {"ordem": 3, "nome": "criar rascunhos de conhecimento para aprovação", "ferramenta": "core/knowledge",
         "permissao": "", "deterministico": True},
    ]


def _plano_para(categoria: str, acao: str) -> dict:
    if categoria == "cotacao":
        return {"categoria": categoria, "etapas": _etapas_cotacao(),
                "ferramentas": ["connectors/exchange"], "permisoes": ["ler_api"],
                "riscos": ["fonte externa indisponível", "dado não é contrato"],
                "aprovacao_necessaria": False, "acao": acao}
    if categoria == "navegador":
        return {"categoria": categoria, "etapas": _etapas_leitura(),
                "ferramentas": ["browser/reader"], "permisoes": ["rede", "ler_api"],
                "riscos": ["site não autorizado", "layout mudou", "conteúdo dinâmico"],
                "aprovacao_necessaria": True,
                "acao": acao}
    if categoria in ("pesquisa", "buscar"):
        return {"categoria": categoria, "etapas": _etapas_pesquisa_livre(),
                "ferramentas": ["browser/search", "browser/reader", "core/knowledge"],
                "permisoes": ["rede", "ler_api"],
                "riscos": ["resultados nem sempre permitidos na allowlist",
                           "conteúdo pode estar desatualizado"],
                "aprovacao_necessaria": False, "acao": acao}
    if categoria == "aprendizado":
        return {"categoria": categoria, "etapas": _etapas_aprender_autonomo(),
                "ferramentas": ["core/aprendizado_auto", "core/knowledge"],
                "permisoes": ["ler_api", "rede"],
                "riscos": ["conteúdo de internet não é contrato",
                           "autoaprovação apenas para técnico/público"],
                "aprovacao_necessaria": False, "acao": acao}
    if categoria == "pensar":
        return {"categoria": categoria, "etapas": _etapas_pensar(),
                "ferramentas": ["core/memory", "core/journal"], "permisoes": [],
                "riscos": ["síntese limitada ao que já foi aprendido"],
                "aprovacao_necessaria": False, "acao": acao}
    if categoria == "contexto":
        return {"categoria": categoria, "etapas": _etapas_contexto(),
                "ferramentas": ["core/knowledge"], "permisoes": [],
                "riscos": ["texto grande pode gerar muitos rascunhos"],
                "aprovacao_necessaria": False, "acao": acao}
    if categoria == "banco_de_dados":
        return {"categoria": categoria, "etapas": _etapas_banco(),
                "ferramentas": ["core/execution"], "permisoes": ["ler_db"],
                "riscos": ["consulta sem índice", "dado sensível"],
                "aprovacao_necessaria": False, "acao": acao}
    if categoria == "mensagens":
        return {"categoria": categoria, "etapas": _etapas_mensagens(),
                "ferramentas": ["telegram/bot"], "permisoes": ["mensagens"],
                "riscos": ["envio não autorizado"], "aprovacao_necessaria": True,
                "acao": acao}
    if categoria in ("criar_modulo",):
        return {"categoria": categoria, "etapas": _etapas_criar_modulo(),
                "ferramentas": ["orchestrator/gerador", "core/sandbox_runner", "core/plugin"],
                "permisoes": ["publicacao_modulo"],
                "riscos": ["código arbitrário", "permissões amplas"],
                "aprovacao_necessaria": True, "acao": acao}
    if categoria == "erro":
        return {"categoria": categoria, "etapas": _etapas_erro(),
                "ferramentas": ["core/journal", "economy/llm"], "permisoes": [],
                "riscos": ["diagnóstico incorreto"], "aprovacao_necessaria": False,
                "acao": acao}
    if categoria in ("pedidos", "estoque", "produtos", "vendas", "loja"):
        return {"categoria": categoria, "etapas": _etapas_banco(),
                "ferramentas": ["core/execution"], "permisoes": ["ler_pedidos", "ler_db"],
                "riscos": ["dados comerciais"], "aprovacao_necessaria": False, "acao": acao}
    if categoria == "financeiro":
        return {"categoria": categoria, "etapas": [
            {"ordem": 1, "nome": "BLOQUEADO: pagamento exige humano", "ferramenta": "core/approvals",
             "permissao": "pagamentos", "deterministico": True}],
            "ferramentas": ["core/approvals"], "permisoes": ["pagamentos"],
            "riscos": ["pagamento irreversível"], "aprovacao_necessaria": True, "acao": acao}
    # desconhecida / n8n / android (adaptadores futuros)
    return {"categoria": categoria, "etapas": [
        {"ordem": 1, "nome": f"verificar adaptador '{acao or categoria}'",
         "ferramenta": f"integracao/{categoria}", "permissao": "", "deterministico": False}],
        "ferramentas": [f"integracao/{categoria}"], "permisoes": [],
        "riscos": ["adaptador não implementado no MVP"],
        "aprovacao_necessaria": False, "acao": acao}


def planejar(pedido: str, classificacao: Classificacao) -> dict:
    """Gera plano determinístico (templates) OU devolve pedido de desambiguação."""
    if classificacao.categoria == "desconhecida" or ambiguidade(pedido):
        return {"status": "precisa_desambiguacao",
                "perguntas": PERGUNTAS_DESAMBIGUACAO,
                "classificacao": classificacao.categoria}
    plano = _plano_para(classificacao.categoria, classificacao.acao)
    cfg = carregar_config()
    ferramenta_existente = None
    if plano["ferramentas"]:
        candidato = versao_atual(plano["ferramentas"][0].split("/")[-1])
        ferramenta_existente = bool(candidato)
    plano.update({
        "status": "plano",
        "objetivo": pedido,
        "ferramenta_existente": ferramenta_existente,
        "modo": cfg.modo,
        "custo_estimado": {"chamadas_ia": 0 if ferramenta_existente is not False else 1,
                           "alerta": "modo teste: nenhuma ação externa real"},
    })
    return plano