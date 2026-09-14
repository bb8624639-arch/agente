"""Camada de persistência.

Ponto único de acesso ao banco. No MVP usa SQLite (stdlib), mas a interface é
feita para ser substituída por um adaptador PostgreSQL/Supabase sem tocar no resto:
troque `connect`/`_executar` por uma conexão SQL parametrizada equivalente.

Regras:
- Credenciais jamais são persistidas; apenas referências (ex.: "env:TELEGRAM_BOT_TOKEN").
- Toda escrita em tabelas de módulos/execuções fica no mesmo banco (transacional).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ..config import BANCO, PASTA_ESTADO

_locais = threading.local()


def _conexao() -> sqlite3.Connection:
    if getattr(_locais, "conexao", None) is None:
        PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
        conexao = sqlite3.connect(BANCO, timeout=10)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA journal_mode=WAL")
        conexao.execute("PRAGMA foreign_keys=ON")
        _locais.conexao = conexao
        _criar_esquema(conexao)
    return _locais.conexao


@contextmanager
def transacao() -> Iterator[sqlite3.Connection]:
    conexao = _conexao()
    try:
        yield conexao
        conexao.commit()
    except BaseException:
        conexao.rollback()
        raise


def executar(sql: str, params: tuple = ()) -> None:
    with _conexao() as conexao:
        conexao.execute(sql, params)
        conexao.commit()


def consultar(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _conexao() as conexao:
        linhas = conexao.execute(sql, params).fetchall()
    return [dict(linha) for linha in linhas]


def consultar_um(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    linhas = consultar(sql, params)
    return linhas[0] if linhas else None


def _criar_esquema(conexao: sqlite3.Connection) -> None:
    conexao.executescript(
        """
        CREATE TABLE IF NOT EXISTS modulos (
            nome            TEXT NOT NULL,
            versao          TEXT NOT NULL,
            perfil          TEXT NOT NULL DEFAULT 'rascunho',  -- rascunho|publicado
            manifesto       TEXT NOT NULL,                      -- JSON canônico
            status          TEXT NOT NULL DEFAULT 'ativo',      -- ativo|inativo|excluido
            aprovado        INTEGER NOT NULL DEFAULT 0,
            criado_em       REAL NOT NULL,
            PRIMARY KEY (nome, versao)
        );

        CREATE TABLE IF NOT EXISTS versoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nome            TEXT NOT NULL,
            versao          TEXT NOT NULL,
            acao            TEXT NOT NULL,     -- publicar|rollback|desativar|reativar
            de_versao       TEXT,
            para_versao     TEXT,
            motivo          TEXT DEFAULT '',
            por             TEXT DEFAULT 'agente',
            criado_em       REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS execucoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo          TEXT NOT NULL,
            versao          TEXT,
            plano           TEXT,               -- JSON
            status          TEXT NOT NULL,     -- ok|falha|bloqueada|cancelada
            entrada         TEXT,
            resultado       TEXT,
            erro            TEXT,
            consumo         TEXT,              -- JSON: chamadas_ia, tokens, custo_estimado, paginas
            aprovacao       TEXT DEFAULT '',   -- referencia à aprovação, se exigida
            criado_em       REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS aprovacoes (
            id              TEXT PRIMARY KEY,  -- uuid textual
            acao            TEXT NOT NULL,
            modulo          TEXT,
            contexto        TEXT,
            status          TEXT NOT NULL DEFAULT 'pendente',  -- pendente|aprovado|recusado|bloqueado
            decidido_por    TEXT DEFAULT '',
            decidido_em     REAL,
            criado_em       REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS consumo (
            periodo        TEXT NOT NULL,       -- dia:YYYY-MM-DD | mes:YYYY-MM | tarefa:uuid
            chamadas_ia    INTEGER NOT NULL DEFAULT 0,
            tokens_in      INTEGER NOT NULL DEFAULT 0,
            tokens_out     INTEGER NOT NULL DEFAULT 0,
            custo_r        REAL NOT NULL DEFAULT 0,
            paginas        INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (periodo)
        );

        CREATE TABLE IF NOT EXISTS diario (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo          TEXT NOT NULL DEFAULT 'info',  -- info|decisao|erro|correcao|handoff
            mensagem      TEXT NOT NULL,
            dados         TEXT DEFAULT '{}',
            criado_em     REAL NOT NULL
        );
        """
    )


# ----------------------------------------------------------------------
# Helpers de JSON (linhas ficam em JSONB/torna Text; migração direta ao Postgres)
def j_dumps(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def j_loads(texto: str | None, padrao: Any = None) -> Any:
    if texto is None or texto == "":
        return padrao
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return padrao