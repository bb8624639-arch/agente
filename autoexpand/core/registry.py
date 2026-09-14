"""Registro versionado de módulos.

Invariantes:
- publicar NUNCA sobrescreve a versão estável: cria novo par (nome, versao);
- `versao_atual(nome)` devolve a maior versão **publicada e ativa**;
- rollback troca a versão ativa para uma versão anterior (reversível);
- todas as ações ficam na tabela `versoes` (histórico auditável).

Versionamento: semver simples `MAJOR.MINOR.PATCH`; comparação numérica.
"""

from __future__ import annotations

import time
from typing import Any

from ..config import MODO_PADRAO
from .persistence import consultar, consultar_um, executar, j_dumps, j_loads
from .plugin import Modulo, normalizar_manifesto
from .permissions import APROVACAO_MINIMA_OBRIGATORIA


class ErroRegistro(Exception):
    pass


def _semver(chave: tuple[str, ...]) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in chave[1].split("."))
    except (TypeError, ValueError):
        return (0, 0, 0)


def registrar_manifesto(manifesto: dict) -> dict:
    """Registra (idempotente por nome+versao) e devolve o manifesto canônico."""
    m = normalizar_manifesto(manifesto)
    existente = consultar_um(
        "SELECT nome, versao FROM modulos WHERE nome=? AND versao=?",
        (m["nome"], m["versao"]))
    if existente:
        return m
    executar(
        """INSERT INTO modulos (nome, versao, perfil, manifesto, status, aprovado, criado_em)
           VALUES (?,?,?,?,?,?,?)""",
        (m["nome"], m["versao"], m["perfil"], j_dumps(m),
         "ativo", 1 if m.get("aprovado") else 0, time.time()))
    return m


def publicar(nome: str, manifesto: dict, *, por: str = "agente",
             aprovado: bool = False, motivo: str = "nova versão") -> dict:
    """Registra e marca como publicado. Quem chama é responsável pela aprovação.

    A versão estável atual NÃO é alterada; a nova versão passa a ser a atual
    (a mais alta publicada). Rollback é possível via `rollback`.
    """
    m = registrar_manifesto(manifesto)
    if m["perfil"] == "rascunho":
        executar("UPDATE modulos SET perfil='publicado', aprovado=?, status='ativo' "
                 "WHERE nome=? AND versao=?",
                 (1 if aprovado else int(m.get("aprovado", False)), nome, m["versao"]))
        m["perfil"] = "publicado"
        m["aprovado"] = aprovado or bool(m.get("aprovado"))
    executar(
        "INSERT INTO versoes (nome, versao, acao, para_versao, motivo, por, criado_em) "
        "VALUES (?,?, 'publicar', ?, ?, ?, ?)",
        (nome, m["versao"], m["versao"], motivo, por, time.time()))
    return m


def versao_atual(nome: str) -> dict[str, Any] | None:
    """Maior versão publicada e ativa (status != excluido)."""
    linhas = consultar(
        "SELECT manifesto, versao, aprovado FROM modulos WHERE nome=? AND perfil='publicado' "
        "AND status='ativo'",
        (nome,))
    if not linhas:
        return None
    melhor = max(linhas, key=lambda r: _semver((nome, r["versao"])))
    m = j_loads(melhor["manifesto"])
    m["aprovado"] = bool(melhor["aprovado"])
    return m


def modulo_por_versao(nome: str, versao: str) -> dict[str, Any] | None:
    linha = consultar_um("SELECT manifesto, aprovado FROM modulos WHERE nome=? AND versao=?",
                         (nome, versao))
    if not linha:
        return None
    m = j_loads(linha["manifesto"])
    m["aprovado"] = bool(linha["aprovado"])
    return m


def _proxima_versao_patch(nome: str) -> str:
    atual = versao_atual(nome)
    if not atual:
        return "1.0.0"
    partes = [int(p) for p in atual["versao"].split(".")][:3]
    partes[2] += 1
    return ".".join(str(p) for p in partes)


def nova_versao_corretiva(nome: str, manifesto_delta: dict) -> str:
    """Aplica mudança sobre a versão estável e devolve a próxima versão (não registra)."""
    base = versao_atual(nome) or {"versao": "1.0.0"}
    nova = dict(base)
    nova.update(manifesto_delta)
    nova["versao"] = _proxima_versao_patch(nome)
    return nova["versao"]


def rollback(nome: str, para_versao: str | None = None, *, por: str = "agente",
             motivo: str = "rollback") -> dict[str, Any]:
    """Marca a versão atual como inativa e ativa a versão alvo (ou a 2ª mais alta).

    Retorna o manifesto que passou a ser ativo.
    """
    atual = versao_atual(nome)
    if not atual:
        raise ErroRegistro(f"não há versão publicada para {nome!r}")
    de_versao = atual["versao"]

    if para_versao is None:
        candidatas = [linha for linha in consultar(
            "SELECT versao FROM modulos WHERE nome=? AND perfil='publicado' "
            "AND status='ativo'", (nome,)) if linha["versao"] != de_versao]
        if not candidatas:
            raise ErroRegistro("não existe versão anterior para rollback")
        alvo = max(candidatas, key=lambda r: _semver((nome, r["versao"])))["versao"]
    else:
        alvo = para_versao

    executar("UPDATE modulos SET status='inativo' WHERE nome=? AND versao=?",
             (nome, de_versao))
    executar("UPDATE modulos SET status='ativo' WHERE nome=? AND versao=?",
             (nome, alvo))
    executar("INSERT INTO versoes (nome, versao, acao, de_versao, para_versao, motivo, por, criado_em) "
             "VALUES (?,?, 'rollback', ?, ?, ?, ?, ?)",
             (nome, de_versao, de_versao, alvo, motivo, por, time.time()))
    return modulo_por_versao(nome, alvo) or {}


def desativar(nome: str, *, por: str = "agente", motivo: str = "") -> None:
    atual = versao_atual(nome)
    if not atual:
        raise ErroRegistro(f"não há versão publicada para {nome!r}")
    executar("UPDATE modulos SET status='inativo' WHERE nome=? AND versao=?",
             (nome, atual["versao"]))
    executar("INSERT INTO versoes (nome, versao, acao, motivo, por, criado_em) "
             "VALUES (?,?, 'desativar', ?, ?, ?)",
             (nome, atual["versao"], motivo, por, time.time()))


def reativar(nome: str, *, por: str = "agente", motivo: str = "") -> None:
    linha = consultar_um(
        "SELECT nome, versao FROM modulos WHERE nome=? AND perfil='publicado' "
        "ORDER BY versao DESC LIMIT 1", (nome,))
    if not linha:
        raise ErroRegistro(f"não há versão publicada para {nome!r}")
    executar("UPDATE modulos SET status='ativo' WHERE nome=? AND versao=?",
             (nome, linha["versao"]))
    executar("INSERT INTO versoes (nome, versao, acao, motivo, por, criado_em) "
             "VALUES (?,?, 'reativar', ?, ?, ?)",
             (nome, linha["versao"], motivo, por, time.time()))


def excluir_modulo(nome: str, *, por: str = "agente", motivo: str = "") -> dict:
    """Exclusão lógica (nunca apaga histórico). Exige aprovação na camada de cima."""
    executar("UPDATE modulos SET status='excluido' WHERE nome=?", (nome,))
    executar("INSERT INTO versoes (nome, versao, acao, motivo, por, criado_em) "
             "VALUES (?, '', 'excluir_modulo', ?, ?, ?)",
             (nome, motivo, por, time.time()))
    return {"excluidos": consultar("SELECT nome, versao FROM modulos WHERE nome=?", (nome,))}


def listar_modulos(perfil: str | None = None, incluir_excluidos: bool = False) -> list[dict]:
    sql = "SELECT nome, versao, perfil, manifesto, status, aprovado, criado_em FROM modulos"
    params: tuple = ()
    clausulas = []
    if not incluir_excluidos:
        clausulas.append("status != 'excluido'")
    if perfil:
        clausulas.append("perfil=?")
        params = (perfil,)
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    linhas = consultar(sql + " ORDER BY nome, versao", params)
    saida = []
    for r in linhas:
        m = j_loads(r["manifesto"], {})
        m["status"] = r["status"]
        m["aprovado"] = bool(r["aprovado"])
        saida.append(m)
    return saida


def historico_versoes(nome: str | None = None) -> list[dict]:
    if nome:
        sql = "SELECT * FROM versoes WHERE nome=? ORDER BY id DESC"
        params = (nome,)
    else:
        sql = "SELECT * FROM versoes ORDER BY id DESC LIMIT 200"
        params = ()
    return consultar(sql, params)


def exigencia_de_aprovacao(modulo: dict) -> tuple[bool, list[str]]:
    """(exige, motivos). Permissões sempre-humanas ou com efeito colateral exigem."""
    motivos: list[str] = []
    for p in modulo.get("permissoes", []):
        if p in APROVACAO_MINIMA_OBRIGATORIA or p.startswith("escrever_") or p == "navegador":
            motivos.append(f"permissão sensível: {p}")
    if modulo.get("perfil") == "publicado" and not motivos:
        # Publicar em produção é sempre aprovável quando há efeito; leitura pura não.
        motivos = ["módulo publicado sem aprovação prévia registrada"]
    return (bool(motivos), motivos)


def register_default(permitidas_globais: set[str] | None = None) -> set[str]:
    """Permissões globais default do sistema (configurável via env/arquivo)."""
    if permitidas_globais is not None:
        return set(permitidas_globais)
    from .permissions import AUTO_APROVADAS
    return set(AUTO_APROVADAS) | {"rede"}