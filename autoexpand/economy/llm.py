"""Adaptador de LLM independente de provedor.

Interface única para o resto do sistema. O provedor real é selecionado por env:
AE_LLM_BASE_URL (formato OpenAI-compatible), AE_LLM_API_KEY, AE_LLM_MODEL_BARATO,
AE_LLM_MODEL_AVANCADO. Sem chave → `disponivel()==False` e todas as funções caem
em regras/templates determinísticos (economia de créditos).

Nenhuma credencial é logada: os pedidos/respostas registrados via journal são
só métricas (contagem/tokens) — sem conteúdo.

Funções de classificação/extração/roteamento usam o modelo barato configurado;
planejamento/geração de código/diagnóstico difícil usam o avançado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..core import budget, journal

BASE_URL = os.environ.get("AE_LLM_BASE_URL", "")
API_KEY = os.environ.get("AE_LLM_API_KEY", "")
MODELO_BARATO = os.environ.get("AE_LLM_MODEL_BARATO", "gemini-2.0-flash")
MODELO_AVANCADO = os.environ.get("AE_LLM_MODEL_AVANCADO", "gpt-4o-mini")
TEM_LLM = bool(BASE_URL and API_KEY)

# Custo estimado por milháo de tokens (R$), por modelo (para o journal).
# Valores conservadores/ajustáveis — usados apenas p/ contabilizar estimativa.
CUSTO_POR_MILHAO: dict[str, float] = {
    "gemini-2.0-flash": 0.80,   # barato (classificação)
    "gpt-4o-mini": 2.50,        # avançado (planejamento/geração)
}
CUSTO_PADRAO_BARATO = 1.0
CUSTO_PADRAO_AVANCADO = 3.0


@dataclass
class ChamadaLLM:
    modelo: str
    motivo: str
    prompt_reduzido_caracteres: int
    tokens_entrada: int
    tokens_saida: int
    custo_r: float
    resposta: str = ""


def _estimar_tokens(texto: str) -> int:
    # heurística barata (~4 chars/token), suficiente p/ estimativas
    return max(1, len(texto) // 4)


def _custo_por_milhao(modelo: str) -> float:
    return CUSTO_POR_MILHAO.get(modelo, CUSTO_PADRAO_BARATO)


def _chamar(prompt: str, modelo: str, motivo: str, temperatura: float = 0.0,
            max_saida: int = 2000) -> ChamadaLLM:
    """Faz chamada real (se habilitada) ou devolve resposta vazia (modo sem IA)."""
    import json
    import urllib.request

    registro = ChamadaLLM(modelo=modelo, motivo=motivo)
    if not TEM_LLM:
        registro.resposta = ""
        return registro

    body = json.dumps({
        "model": modelo, "temperature": temperatura,
        "max_tokens": max_saida,
        "messages": [{"role": "user", "content": prompt[:16000]}]  # contexto reduzido
    }).encode()
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/chat/completions",
                                 data=body)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    tokens_entrada = _estimar_tokens(prompt[:16000])
    with urllib.request.urlopen(req, timeout=60) as resp:
        dados = json.load(resp)
    texto = dados["choices"][0]["message"]["content"] or ""
    tokens_saida = int(dados.get("usage", {}).get("completion_tokens", _estimar_tokens(texto)))
    tokens_entrada = int(dados.get("usage", {}).get("prompt_tokens", tokens_entrada))
    registro.tokens_entrada = tokens_entrada
    registro.tokens_saida = tokens_saida
    registro.resposta = texto
    _registrar_consumo(registro, motivo)
    return registro


def _registrar_consumo(llamada: ChamadaLLM, motivo: str) -> None:
    custo = ((llamada.tokens_entrada + llamada.tokens_saida) / 1_000_000) * \
        _custo_por_milhao(llamada.modelo)
    llamada.custo_r = custo
    budget.registrar_uso(chamadas_ia=1, tokens_in=llamada.tokens_entrada,
                         tokens_out=llamada.tokens_saida, custo_r=custo)
    journal.registrar_diario("info", "chamada LLM",
                             {"modelo": llamada.modelo, "motivo": motivo,
                              "tokens_in": llamada.tokens_entrada,
                              "tokens_out": llamada.tokens_saida,
                              "custo_r": round(custo, 4)})


def barato(prompt: str, motivo: str, *, max_saida: int = 500) -> str:
    """Modelo econômico: classificação, extração, roteamento, decisões simples."""
    chamada = _chamar(prompt, MODELO_BARATO, motivo, temperatura=0.0, max_saida=max_saida)
    return chamada.resposta


def avancado(prompt: str, motivo: str, *, max_saida: int = 3000) -> str:
    """Modelo avançado: planejamento complexo, geração de código, diagnóstico."""
    chamada = _chamar(prompt, MODELO_AVANCADO, motivo, temperatura=0.2, max_saida=max_saida)
    return chamada.resposta


def disponivel() -> bool:
    return TEM_LLM