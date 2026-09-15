"""Classificador de intenção — 100% regras (zero IA no caminho quente).

Mapas simples de palavras-chave para categorias. Custo: O(n). Se nada casar,
devolve a categoria `desconhecida` e a lista de perguntas para desambiguação
(sem nunca inventar uma ação).
"""

from __future__ import annotations

import re
from typing import NamedTuple


class Classificacao(NamedTuple):
    categoria: str
    acao: str          # classe de ação p/ política de aprovação
    confianca: float
    sinal: str         # pista que causou o match


_REGISTROS = [
    # (regex, categoria, acao, confianca)
    # ---- comandos explícitos de alta confiança (vencem domínio genérico) ----
    (r"\b(pesquise|pesquisar?|busque|buscar|procure|procurar|pesquisa na internet|aperte o bot[aã]o de pesquisa|fa[aç]a uma pesquisa)\b",
     "pesquisa", "ler", 0.98),
    (r"\b(aprenda|aprender|aprenda sobre|estudar|estude|aprender automaticamente|aprenda aut[oô]nom|aprendizado aut[oô]nomo|aprender sozinho|aprender sem aprova[cç][aã]o|autoaprendi?z[ao])\b",
     "aprendizado", "aprender", 0.97),
    (r"\b(o que voc[eê] sabe|o que voc[eê] aprendeu|me conte o que|me diga o que voc[eê] sabe|resuma o que|fale sobre o que|fale sobre tudo|tudo que sabe|sintetize|pense sobre|pense|pensar|raciocine|insight|vis[aã]o geral)\b",
     "pensar", "ler", 0.98),
    (r"\b(importar contexto|colei aqui|contexto colado|documento abaixo|leia isto|leia o texto|guia abaixo|vou colar)\b",
     "contexto", "ler", 0.95),
    # ---- regras existentes ----
    (r"\b(cota[çc][ãa]o|c[aâ]mbio|d[oó]lar|dolar|usd|brl|euro|moeda|convers[ãa]o de moeda)\b",
     "cotacao", "ler", 0.95),
    (r"\b(pre[çc]o|valor|cota[çc][ãa]o|consulta[rv]|buscar|pesquisa[rv]|coletar|extrair)\b",
     "pesquisa", "ler", 0.8),
    (r"\b(navegador|browser|site|p[aá]gina|scrap(a|e|ing)|raspagem|url|html)\b",
     "navegador", "ler_site", 0.8),
    (r"\b(pedid|order)\b", "pedidos", "ler_pedidos", 0.8),
    (r"\b(estoque|stock)\b", "estoque", "ler_db", 0.7),
    (r"\b(venda|vender|vendas|crm|cliente|lead)\b", "vendas", "ler_pedidos", 0.7),
    (r"\b(produto|catalogo|cat[aá]logo)\b", "produtos", "ler_db", 0.7),
    (r"\b(marketing|campanha|an[úu]ncio|divulg[açã]o)\b", "marketing", "publicar_conteudo", 0.7),
    (r"\b(android|celular|telefone|app)\b", "android", "sistema", 0.8),
    (r"\b(n8n|workflow|fluxo)\b", "n8n", "criar_workflow", 0.9),
    (r"\b(banco de dados|database|sql|postgres|sqlite|supabase)\b", "banco_de_dados", "ler_db", 0.8),
    (r"\b(loja|shopify|woocommerce|tiny|bling|ecommerce|e-commerce)\b",
     "loja", "ler_db", 0.7),
    (r"\b(script|plugin|m[oó]dulo|ferramenta|criar agente|novo agente)\b",
     "criar_modulo", "criar_modulo", 0.6),
    (r"\b(pagamento|pix|reembolso|cart[ãa]o|fatura|boleto)\b",
     "financeiro", "pagamento", 0.9),
    (r"\b(mensagem|whatsapp|telegram|slack|email|e-mail)\b",
     "mensagens", "enviar_mensagem", 0.95),
    (r"\b(envi[ao]r?|manda[rvr]?|em massa|avis[ao]r?|notifi(car|que))\b",
     "mensagens", "enviar_mensagem", 0.85),
    (r"\b(whatsapp)\b", "mensagens", "enviar_mensagem", 0.7),
    (r"\b(erro|falha|bug|log|diagn[oó]stico|exception|traceback)\b",
     "erro", "diagnosticar", 0.8),
    (r"\b(aprender|pesquis[ar]?|buscar|procurar|estudar|conhecimento|me ensina|o que [ée]|o que sao|explique|resuma)\b",
     "pesquisa", "ler", 0.65),
    (r"\b(pensar|pense|raciocinar|insight|s[ií]ntese|o que voce sabe|me diga o que|vis[ãa]o geral)\b",
     "pensar", "ler", 0.7),
    (r"\b(contexto|colar|documento|text[oó] colado|importar|guia|manual)\b",
     "contexto", "ler", 0.7),
]

PERGUNTAS_DESAMBIGUACAO = [
    "O pedido não mencionou uma categoria suportada. O que você quer fazer?",
    "  1) consultar preço/valor em site autorizado",
    "  2) automatizar navegador (ler página)",
    "  3) mexer com pedidos/estoque/banco",
    "  4) enviar mensagem (Telegram/WhatsApp/e-mail)",
    "  5) criar script/plugin/agente novo",
    "  6) diagnosticar erro",
    "  7) pagamento/Pix",
    "  8) outra coisa (descreva)",
]


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.lower().strip())


def classificar(pedido: str) -> Classificacao:
    """Devolve a melhor classificação por regras. Sempre retorna algo."""
    texto = normalizar(pedido)
    melhor: Classificacao | None = None
    for regex, categoria, acao, confianca in _REGISTROS:
        if re.search(regex, texto):
            candidata = Classificacao(categoria, acao, confianca, regex)
            if melhor is None or candidata.confianca > melhor.confianca:
                melhor = candidata
    if melhor is None:
        return Classificacao("desconhecida", "nao_identificado", 0.0, "")
    return melhor


FAMILIAS: dict[str, str] = {
    "pesquisa": "leitura", "navegador": "leitura", "banco_de_dados": "leitura",
    "pedidos": "leitura", "estoque": "leitura", "produtos": "leitura",
    "vendas": "leitura", "loja": "leitura", "contexto": "leitura",
    "aprendizado": "raciocinio",
    "pensar": "raciocinio",
    "mensagens": "comunicacao",
    "criar_modulo": "criacao", "n8n": "criacao",
    "financeiro": "pagamento",
    "erro": "diagnostico",
    "android": "dispositivo",
}


def ambiguidade(pedido: str) -> bool:
    """Retorna True só se duas FAMÍLIAS distintas brigam com confiança próxima.

    Palavras de leitura (preço+site+produto) não geram ambiguidade entre si.
    Critério rígido: >= 2 famílias, confiança mínima 0.65, diferença < 0.12.
    """
    texto = normalizar(pedido)
    por_familia: dict[str, float] = {}
    for regex, categoria, _acao, confianca in _REGISTROS:
        if re.search(regex, texto):
            familia = FAMILIAS.get(categoria, categoria)
            por_familia[familia] = max(por_familia.get(familia, 0.0), confianca)
    valores = sorted(por_familia.values(), reverse=True)
    if len(valores) >= 2 and valores[0] >= 0.65 and valores[1] >= 0.65:
        return valores[0] - valores[1] < 0.12
    return False