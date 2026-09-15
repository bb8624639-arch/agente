"""Memória de aprendizado do agente: conhecimento registrado pelo usuário,
extraído da internet ou proposto pelo próprio agente — sempre com aprovação.

Fluxo (supervisão):
  1. registrar(topico, conteudo, origem) -> cria rascunho
  2. o usuário aprova/rejeita via painel ou Telegram (/aprovar <id>)
  3. apenas conhecimento 'aprovado' é usado em decisões futuras

Fonte de aprendizado externo: Wikipedia REST (pública, sem chave),
limitada a artigos de domínio aberto — nada sensível é armazenado sem revisão.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from textwrap import wrap

from .persistence import consultar, executar, j_loads

ORIGENS = ("usuario", "internet", "agente")
STATUS = ("rascunho", "aprovado", "rejeitado")

# Wikipedia REST: busca + resumo (extrato do primeiro parágrafo)
_WIKI_BASE = "https://pt.wikipedia.org/api/rest_v1/page/summary/"
_UA = {"User-Agent": "AgenteOrquestrador/1.0 (contato: admin@localhost)"}


def registrar(topico: str, conteudo: str, *, origem: str = "usuario", fonte: str = "") -> int:
    """Cria um rascunho de conhecimento. Devolve o id para aprovação.

    Conteúdo maior é aceito (contexto colado): até 30k caracteres para "usuario",
    para suportar importar documentos inteiros. Tópicos continuam curtos.
    """
    topico = topico.strip()[:300]
    antecedente = conteudo.strip()
    # limite generoso p/ lidar com texto colado; internet/agente ficam em 4000
    limite = 30000 if origem == "usuario" else 8000
    conteudo = antecedente[:limite]
    if origem not in ORIGENS:
        origem = "usuario"
    if not topico or not conteudo:
        raise ValueError("tópico e conteúdo são obrigatórios")
    executar(
        """INSERT INTO conhecimento (topico, conteudo, fonte, status, origem, criado_em)
           VALUES (?,?,?,?,?,?)""",
        (topico, conteudo, fonte[:500], "rascunho", origem, time.time()))
    return consultar("SELECT id FROM conhecimento ORDER BY id DESC LIMIT 1")[0]["id"]


def listar(status: str | None = "aprovado") -> list[dict]:
    """Lista conhecimentos. status=None -> todos. Padrão otimista: só aprovados."""
    if status not in STATUS and status is not None:
        raise ValueError(f"status inválido: {status}")
    if status is None:
        sql = "SELECT * FROM conhecimento ORDER BY id DESC"
        params: tuple = ()
    else:
        sql = "SELECT * FROM conhecimento WHERE status=? ORDER BY id DESC"
        params = (status,)
    return consultar(sql, params)


def decidir(id_conh: int, aprovado: bool, *, por: str = "agente") -> dict:
    """Aprova ou rejeita um rascunho de conhecimento. Registra auditoria no diário."""
    encontrado = consultar("SELECT * FROM conhecimento WHERE id=?", (id_conh,))
    if not encontrado:
        return {"status": "inexistente", "id": id_conh}
    novo = "aprovado" if aprovado else "rejeitado"
    executar(
        """UPDATE conhecimento SET status=?, aprovado_por=?, aprovado_em=?
           WHERE id=?""",
        (novo, por, time.time(), id_conh))
    item = encontrado[0]
    from .journal import registrar_diario
    registrar_diario(
        "decisao", f"conhecimento #{id_conh} {novo} por {por}",
        {"topico": item["topico"], "aprovado": aprovado})
    return {"status": novo, "id": id_conh, "topico": item["topico"]}


def buscar_completo(topico: str, limite_palavras: int = 150) -> dict:
    """Pesquisa resumo na Wikipedia (pt) e devolve candidato a conhecimento.

    Só cria rascunho se o artigo existir (status 200). Falha retorna dict com 'erro'.
    """
    topico_limpo = topico.strip()
    if not topico_limpo:
        return {"erro": "tópico vazio"}
    enc = urllib.parse.quote(topico_limpo.replace(" ", "_"))
    url = _WIKI_BASE + enc
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"erro": f"falha ao consultar fonte: {exc}"}

    titulo = dados.get("title", topico_limpo)
    descricao = (dados.get("extract") or "").strip()
    if not descricao:
        return {"erro": f"sem resumo encontrado para '{topico_limpo}'"}
    resumo = " ".join(descricao.split())[:limite_palavras]
    return {
        "topico": titulo,
        "conteudo": resumo,
        "fonte": (dados.get("content_urls") or {}).get("desktop", {}).get("page", url),
        "origem": "internet",
    }


def aprender_e_registrar(topico: str) -> dict:
    """Busca na internet e cria rascunho aguardando sua aprovação.

    Primeiro tenta Wikipedia; se falhar (sem artigo), faz fallback para
    a busca genérica (DuckDuckGo) e usa o melhor snippet disponível.
    """
    candidato = buscar_completo(topico)
    if "erro" in candidato:
        # fallback: busca livre (se houver fonte autorizada p/ registro)
        candidato = buscar_completo_via_web(topico)
    if "erro" in candidato:
        return candidato
    id_criado = registrar(
        candidato["topico"], candidato["conteudo"],
        origem="internet", fonte=candidato["fonte"])
    return {
        "id": id_criado,
        "topico": candidato["topico"],
        "fonte": candidato["fonte"],
        "conteudo": candidato["conteudo"],
        "aviso": "rascunho criado — aguardando sua aprovação (/aprovar <id>)",
    }


def buscar_completo_via_web(topico: str, limite: int = 3) -> dict:
    """Fallback: usa DuckDuckGo p/ montar um rascunho de conhecimento.

    Usa os snippets dos resultados para compor um resumo. Nunca abre página
    fora da allowlist; só aproveita o que a própria busca retorna.
    """
    try:
        from ..browser.search import buscar_web
        dados = buscar_web(topico, limite=limite)
    except Exception as exc:
        return {"erro": f"fallback de busca falhou: {exc}"}
    if "erro" in dados:
        return {"erro": dados["erro"]}
    resultados = dados.get("resultados", [])
    if not resultados:
        return {"erro": f"nada encontrado na internet para '{topico}'"}
    trechos = [r.get("trecho", "") for r in resultados if r.get("trecho")]
    conteudo = " ".join(trechos)[:4000]
    if not conteudo:
        conteudo = "; ".join(r.get("titulo", "") for r in resultados[:3])[:4000]
    topico_titulo = resultados[0].get("titulo", topico)
    return {
        "topico": topico_titulo,
        "conteudo": conteudo or topico,
        "fonte": resultados[0].get("url", "duckduckgo"),
        "origem": "internet",
    }