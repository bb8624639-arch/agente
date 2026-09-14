"""Roteador econômico: regras → LLM barato → LLM avançado, com cache.

Fluxo ideal (documentado pelo usuário):
   Pedido → regra simples verifica solução determinística
            ├── Sim → código/regra, sem IA
            └── Não → modelo econômico classifica
                        ├── simples → fluxo executável
                        └── complexo → modelo avançado

Cache: chave determinística (hash do pedido normalizado). Resultados
repetidos não gastam chamada.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from ..config import PASTA_ESTADO
from . import llm

_CACHE_ARQUIVO = PASTA_ESTADO / "cache_rotas.json"
_cache: dict[str, dict] = {}


def _carregar_cache() -> dict[str, dict]:
    if _cache:
        return _cache
    if _CACHE_ARQUIVO.exists():
        try:
            _cache.update(json.loads(_CACHE_ARQUIVO.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            _cache.clear()
    return _cache


def _salvar_cache() -> None:
    PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
    _CACHE_ARQUIVO.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")


def chave_cache(*partes: Any) -> str:
    plano = "|".join(_resumir(p) for p in partes)
    return hashlib.sha256(plano.encode()).hexdigest()


def _resumir(v: Any) -> str:
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return str(v)


def get_cached(chave: str) -> dict | None:
    _carregar_cache()
    entrada = _cache.get(chave)
    if not entrada:
        return None
    if entrada.get("expira") and entrada["expira"] < time.time():
        return None
    return entrada


def put_cached(chave: str, valor: dict, ttl_s: int = 3600) -> None:
    _cache[chave] = {"valor": valor, "expira": time.time() + ttl_s}
    _salvar_cache()


def rotear(pedido_str: str, *, funcao_regra: Callable[[str], Any] | None = None,
           funcao_llm_barato: Callable[[str], Any] | None = None,
           funcao_llm_avancado: Callable[[str], Any] | None = None) -> dict:
    """Executa a regra; se não resolver, usa LLM barato; se não, avançado.

    - Regra nula = não resolveu (precisa de IA).
    - LLM barato nulo = não resolveu.
    - A resposta sempre é cacheadada por chave do pedido.
    """
    chave = chave_cache(pedido_str)
    cache = get_cached(chave)
    if cache:
        return {"fonte": "cache", "resultado": cache["valor"]}

    if funcao_regra is not None:
        r = funcao_regra(pedido_str)
        if _nao_nulo(r):
            put_cached(chave, r)
            return {"fonte": "regras", "resultado": r}

    if llm.disponivel() and funcao_llm_barato is not None:
        r = funcao_llm_barato(pedido_str)
        if _nao_nulo(r):
            put_cached(chave, r)
            return {"fonte": "llm_barato", "resultado": r}
        # barato não resolveu → avançado (justificado)
        r = funcao_llm_avancado(pedido_str) if funcao_llm_avancado else None
        if _nao_nulo(r):
            put_cached(chave, r)
            return {"fonte": "llm_avancado", "resultado": r}

    return {"fonte": "nao_resolvido", "resultado": None}


def _nao_nulo(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and v.strip() == "":
        return False
    if isinstance(v, dict) and not v:
        return False
    return True