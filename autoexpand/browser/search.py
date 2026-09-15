"""Pesquisa web descentralizada de leitura — permitida sem URL prévia.

Usa DuckDuckGo (API publica de busca de notícias/texto) para achar conteúdo,
cujo domínio é validado contra a allowlist. Em modo `teste`, a busca é
simulada (sem rede) e devolve zero resultados — mesmo comportamento de
`browser/reader`.

Regra de segurança mantida: qualquer link só é *aberto* se o domínio estiver
na allowlist (mesmo em modo autônomo). A busca em si não expõe conteúdo:
devolve titulos + trechos (snippets), que precisam de aprovação para virar
conhecimento (rascunho).
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import re
import json

from ..config import MAX_PAGINAS_POR_EXECUCAO
from ..core import budget, journal
from .allowed import verificar_autorizada, SiteNaoAutorizado

_HTMLSOFT = "DuckDuckBot/1.0; agente-orquestrador/0.1"
_UA = {"User-Agent": _HTMLSOFT}


class ErroBusca(Exception):
    pass


def _resumir(texto: str, limite: int = 500) -> str:
    texto_limpo = " ".join(texto.split())
    return texto_limpo[:limite]


def buscar_web(consulta: str, limite: int = 5) -> dict:
    """Busca no DuckDuckGo (HTML lite) e devolve titulos + snippets.

    Devolve {"resultados": [{"titulo", "url", "trecho"}], "fonte": "duckduckgo"}.
    URLs sempre https; snippets limitados, sem conteúdo integral.
    """
    consulta = consulta.strip()
    if not consulta:
        return {"erro": "consulta vazia"}
    if limite < 1 or limite > MAX_PAGINAS_POR_EXECUCAO * 4:
        limite = min(max(1, limite), MAX_PAGINAS_POR_EXECUCAO * 4)

    budget.verificar_limites(paginas_futuras=1)
    budget.registrar_uso(paginas=1)

    from ..config import carregar_config
    if carregar_config().modo == "teste":
        journal.registrar_execucao(
            modulo="browser.search", status="ok",
            entrada={"consulta": consulta, "modo": "teste"},
            resultado={"simulado": True, "resultados": []},
            consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 1})
        return {"simulado": True, "resultados": [], "fonte": "duckduckgo",
                "aviso": "modo teste: nenhuma busca real executada"}

    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(consulta)
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise ErroBusca(f"falha de rede na busca: {exc}")

    # extração leve: links e snippets do HTML (regex simples, sem framework novo)
    resultados: list[dict] = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url_bruta = m.group(1)
        titulo = re.sub(r"<[^>]+>", "", m.group(2))
        if not url_bruta.startswith("http"):
            continue
        url_limpa = url_bruta
        trecho = ""
        snip = re.search(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html[m.end():], re.S)
        if snip:
            trecho = re.sub(r"<[^>]+>", "", snip.group(1))
        resultados.append({"titulo": _resumir(titulo, 200),
                           "url": url_limpa,
                           "trecho": _resumir(trecho, 500)})
        if len(resultados) >= limite:
            break

    journal.registrar_execucao(
        modulo="browser.search", status="ok",
        entrada={"consulta": consulta},
        resultado={"resultados": len(resultados), "urls": [r["url"] for r in resultados[:5]]},
        consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 1})
    return {"resultados": resultados, "fonte": "duckduckgo"}


def ler_pagina_busca(consulta: str, limite_a_ler: int = 3) -> dict:
    """Busca e abre as primeiras paginas permitidas, concatenando trechos.

    Apenas domínios da allowlist são abertos. Se nada da allowlist aparecer,
    devolve a lista de candidatos para o usuário autorizar (nunca abre).
    """
    dados = buscar_web(consulta, limite=max(5, limite_a_ler * 2))
    if "erro" in dados:
        return dados
    if dados.get("simulado"):
        return dados

    abertos: list[dict] = []
    bloqueados: list[str] = []
    for r in dados.get("resultados", []):
        if len(abertos) >= limite_a_ler:
            break
        url = r.get("url", "")
        try:
            verificar_autorizada(url)
        except SiteNaoAutorizado:
            bloqueados.append(url)
            continue
        from .reader import PedidoLeitura, ErroLeitura, ler_pagina_autorizada
        try:
            pagina = ler_pagina_autorizada(PedidoLeitura(url=url))
        except ErroLeitura as exc:
            continue
        if pagina.get("dados_extraidos"):
            abertos.append({
                "url": url, "titulo": r.get("titulo", ""),
                "trecho": pagina["dados_extraidos"][0],
                "snippet": r.get("trecho", "")})

    return {"resultados": dados.get("resultados", []), "abertos": abertos,
            "bloqueados": bloqueados[:5], "fonte": "duckduckgo"}