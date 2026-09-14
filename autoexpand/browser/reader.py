"""Leitura de página autorizada — modo somente leitura (sem login, sem dados).

No MVP usa `requests` + `BeautifulSoup` (sem executar JavaScript). Genérico:
- URL autorizada;
- seletor ou instrução de leitura;
- limite de páginas (N);
- timeout (s);
- formato de saída.

A saída é sempre um JSON resumido e contável (dados_extraidos, paginas_lidas,
tamanho_pagina, tempo). Nunca envia conteúdo integral.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..config import MAX_PAGINAS_POR_EXECUCAO, TIMEOUT_SCRIPT_S
from ..core import budget, journal
from .allowed import verificar_autorizada, validar_url


class ErroLeitura(Exception):
    pass


@dataclass
class PedidoLeitura:
    url: str
    seletor: str = ""          # CSS seletor; vazio → corpo texto
    instrucao: str = ""        # instrução de leitura (limitada p/ evitar contexto grande)
    max_paginas: int = MAX_PAGINAS_POR_EXECUCAO
    timeout_s: int = TIMEOUT_SCRIPT_S
    formato: str = "json"      # json (padrão) | texto_resumido


def _resumir_texto(texto: str, limite: int = 4000) -> str:
    texto_limpo = " ".join(texto.split())
    return texto_limpo[:limite]


def _extrair_por_seletor(soup, seletor: str) -> list[Any]:
    try:
        selecionados = soup.select(seletor)
    except Exception as exc:  # seletor inválido
        raise ErroLeitura(f"seletor inválido: {exc}") from exc
    itens = []
    for el in selecionados[:50]:
        t = _resumir_texto(el.get_text(" ", strip=True), 1000)
        if t:
            itens.append(t)
    return itens


def ler_pagina_autorizada(pedido: PedidoLeitura) -> dict:
    """Executa leitura respeitando allowlist, limites e orçamento (modo teste = simulado)."""
    import requests
    from bs4 import BeautifulSoup

    verificar_autorizada(pedido.url)
    if pedido.max_paginas < 1 or pedido.max_paginas > MAX_PAGINAS_POR_EXECUCAO:
        raise ErroLeitura(f"max_paginas fora de {1}..{MAX_PAGINAS_POR_EXECUCAO}")
    budget.verificar_limites(paginas_futuras=1)
    budget.registrar_uso(paginas=1)

    inicio = time.monotonic()
    from ..config import carregar_config
    if carregar_config().modo == "teste":
        # Sem ação externa real em modo teste: responde simulado + registra.
        journal.registrar_execucao(
            modulo="browser.reader", status="ok",
            entrada={"url": pedido.url, "modo": "teste"},
            resultado={"simulado": True, "url": pedido.url},
            consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 1})
        return {"simulado": True, "url": pedido.url, "dados_extraidos": [],
                "paginas_lidas": 1, "tamanho_pagina": 0,
                "tempo_s": round(time.monotonic() - inicio, 3),
                "aviso": "modo teste: nenhuma ação externa real executada"}

    try:
        resp = requests.get(validar_url(pedido.url), timeout=pedido.timeout_s,
                            headers={"User-Agent": "agente-orquestrador/0.1"})
    except Exception as exc:
        raise ErroLeitura(f"falha de rede: {exc}") from exc
    if resp.status_code != 200:
        raise ErroLeitura(f"HTTP {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    if pedido.seletor:
        dados = _extrair_por_seletor(soup, pedido.seletor)
    else:
        corpo = soup.find("body") or soup
        dados = [_resumir_texto(corpo.get_text(" ", strip=True), 4000)] if corpo.get_text else []

    resultado = {
        "url": pedido.url,
        "dados_extraidos": dados,
        "paginas_lidas": 1,
        "tamanho_pagina_bytes": len(resp.content),
        "tempo_s": round(time.monotonic() - inicio, 3),
        "formato": pedido.formato,
    }
    journal.registrar_execucao(
        modulo="browser.reader", status="ok",
        entrada={"url": pedido.url, "seletor": pedido.seletor or ""},
        resultado={"dados": dados[:3], "tamanho_pagina": len(resp.content)},
        consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 1})
    return resultado