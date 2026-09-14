"""Diário de execução: log auditável de execuções + registro de consumo.

Toda execução grava: módulo, versão, status, entrada/resposta (resumida),
erro, consumo estimado (chamadas_ia, tokens, custo, páginas), aprovação
usada e justificativa do motivo de chamada de IA (via `motivo_ia`).

Função `registrar_execucao` é o único write de `execucoes`.
Funções `diario` gravam na tabela `diario` (eventos do agente continuamente).
"""

from __future__ import annotations

import json
import time
from typing import Any

from .persistence import executar, consultar, j_dumps

TIPOS_DIARIO = ("info", "decisao", "erro", "correcao", "handoff", "manutencao")


def registrar_execucao(*, modulo: str, plano: dict | None = None, status: str = "ok",
                       entrada: Any = None, resultado: Any = None, erro: str | None = None,
                       consumo: dict | None = None, aprovacao: str = "",
                       acontece_em: float | None = None, versao: str = "") -> int:
    """Grava uma linha de execução. Devolve o id."""
    acontece_em = acontece_em or time.time()
    consumidor = consumo or {"chamadas_ia": 0, "tokens_in": 0, "tokens_out": 0,
                             "custo_r": 0.0, "paginas": 0, "motivos_ia": []}
    executar(
        """INSERT INTO execucoes (modulo, versao, plano, status, entrada, resultado,
                                  erro, consumo, aprovacao, criado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (modulo, versao, j_dumps(plano or {}), status,
         j_dumps(entrada or {}), j_dumps(resultado or {}), erro or "",
         j_dumps(consumidor), aprovacao, acontece_em))
    linha = consultar("SELECT id FROM execucoes ORDER BY id DESC LIMIT 1")[0]
    return int(linha["id"])


def registrar_diario(tipo: str, mensagem: str, dados: dict | None = None) -> None:
    if tipo not in TIPOS_DIARIO:
        tipo = "info"
    executar("INSERT INTO diario (tipo, mensagem, dados, criado_em) VALUES (?,?,?,?)",
             (tipo, mensagem, j_dumps(dados or {}), time.time()))


def diario(tipo: str | None = None, ultimos: int = 100) -> list[dict]:
    sql = "SELECT * FROM diario"
    params: tuple = ()
    if tipo:
        sql += " WHERE tipo=?"
        params = (tipo,)
    sql += " ORDER BY id DESC LIMIT ?"
    return consultar(sql, params + (ultimos,))


def execucoes(modulo: str | None = None, ultimos: int = 50) -> list[dict]:
    sql = "SELECT * FROM execucoes"
    params: tuple = ()
    if modulo:
        sql += " WHERE modulo=?"
        params = (modulo,)
    sql += " ORDER BY id DESC LIMIT ?"
    return consultar(sql, params + (ultimos,))


def resumo_consumo() -> dict:
    """Agrega consumo atual por tarefa/dia/mês (delegado para budget)."""
    from .budget import consumo_consolidado
    return consumo_consolidado()