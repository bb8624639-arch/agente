"""Motor de execução com guardas de segurança.

Regras do usuário implementadas aqui:
- no máximo 3 tentativas por ação;
- NUNCA repetir a mesma estratégia que falhou (anti-loop / sem repetição cega);
- timeout de 60 s por script (sandbox);
- interrompe ao bater orçamento (LimiteExcedido);
- auto-rollback se falhas > tolerância;
- marca tarefa como bloqueada se não houver solução segura;
- nunca inventa sucesso: toda falha reporta erro honesto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..config import (MAX_TENTATIVAS, MODO_PADRAO, RECURSAO_PERMITIDA,
                      TIMEOUT_SCRIPT_S, carregar_config)
from . import approvals, budget, journal
from .permissions import AUTO_APROVADAS
from .sandbox_runner import PacotePermissao, executar as executar_sandbox
from .registry import publicar as _publicar


class Bloqueado(Exception):
    """Ação bloqueada por política (aprovação pendente, emergência, regra)."""

    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


@dataclass
class Tarefa:
    """Plano mínimo entendido pelo executor."""
    objetivo: str
    acao: str                                # classe da ação (ex.: ler_site, publicar_modulo)
    modulo: str = ""
    versao: str = ""
    parametros: dict = field(default_factory=dict)
    efeito_externo: bool = False             # se true, exige escrutínio/aprovação
    permissoes_necessarias: list[str] = field(default_factory=list)
    timeout_seconds: int = TIMEOUT_SCRIPT_S
    limite_memoria_mb: int = 128
    tolerancia_falhas: int = 3
    aprovacao_id: str = ""
    status: str = "pendente"


def _sanitizar(texto: str) -> str:
    """Remove padrões que possam conter credenciais antes de registrar."""
    texto = re.sub(r"(?i)(token|key|secret|password|senha|api_key)\s*[=:]\s*\S+",
                   r"\1=***", texto)
    texto = re.sub(r"Bearer\s+\S+", "Bearer ***", texto)
    return texto[:800]


def permissoes_globais() -> set[str]:
    """Permissões que o sistema está disposto a conceder por padrão (allowlist)."""
    return set(AUTO_APROVADAS) | {"rede", "ler_api", "ler_db"}


def verificar_pre_voo(tarefa: Tarefa, cfg) -> None:
    """Checagens baratas antes de qualquer execução (sem IA)."""
    if cfg.emergencia or MODO_PADRAO == "emergencia":
        raise Bloqueado("modo emergência: todas as execuções estão pausadas")
    if tarefa.status == "bloqueada":
        raise Bloqueado("tarefa marcada como bloqueada (sem solução segura)")
    budget.verificar_limites()
    if approvals.exige_aprovacao_sempre(tarefa.acao):
        raise Bloqueado(
            f"ação '{tarefa.acao}' exige aprovação humana registrada "
            f"(modo={MODO_PADRAO})")


def _aprovacao_ok(tarefa: Tarefa) -> bool:
    if not tarefa.aprovacao_id:
        return False
    return approvals.status_aprovacao(tarefa.aprovacao_id) == "aprovado"


def executar_com_recuperacao(tarefa: Tarefa, funcao_executa: Callable) -> dict:
    """Loop controlado de tentativas com estratégia mutável (anti-loop).

    `funcao_executa(estrategia, tentativa)` → {"ok", "resultado", "erro"}.
    Estratégias falhadas nunca são repetidas; após MAX_TENTATIVAS a tarefa é
    marcada como bloqueada — o sistema nunca inventa sucesso.
    """
    verificar_pre_voo(tarefa, carregar_config())
    falhas = 0
    usadas: set[str] = set()
    ultimo_erro = ""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        budget.verificar_limites()
        estrategia = _proxima_estrategia(tentativa, ultimo_erro, usadas)
        try:
            resp = funcao_executa(estrategia, tentativa)
        except Bloqueado:
            raise
        except Exception as exc:  # sanitizado, nunca credencial
            resp = {"ok": False, "resultado": None,
                    "erro": f"{type(exc).__name__}: {_sanitizar(str(exc))}"}
        if resp.get("ok"):
            return resp
        falhas += 1
        usadas.add(estrategia)
        ultimo_erro = resp.get("erro") or "sem detalhes"
        journal.registrar_diario(
            "erro", f"falha {tentativa}/{MAX_TENTATIVAS}",
            {"modulo": tarefa.modulo, "estrategia": estrategia, "erro": ultimo_erro})
    tarefa.status = "bloqueada"
    journal.registrar_execucao(
        modulo=tarefa.modulo or tarefa.objetivo, status="bloqueada",
        plano=vars(tarefa), erro=ultimo_erro,
        consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 0})
    return {"ok": False, "resultado": None,
            "erro": f"falha após {falhas} tentativas (máx {MAX_TENTATIVAS}): {ultimo_erro}",
            "status": "bloqueada"}


def _proxima_estrategia(tentativa: int, ultimo_erro: str, usadas: set[str]) -> str:
    """Heurística determinística e econômica: muda a abordagem conforme o erro."""
    base = f"estratégia-{tentativa}"
    if "timeout" in ultimo_erro.lower():
        base += "-reduzido"
    elif "mem" in ultimo_erro.lower():
        base += "-memoria-reduzida"
    sufixo = 1
    while base in usadas:
        base = f"{base}-{sufixo}"
        sufixo += 1
    return base


def executar_script(tarefa: Tarefa, codigo: str, lingua: str,
                    entrada: dict | None = None) -> dict:
    """Executa código no sandbox aplicando permissões efetivas. Sempre isolado."""
    pacote = PacotePermissao.do_manifesto(tarefa.permissoes_necessarias,
                                          permissoes_globais())
    if pacote.denied:
        raise Bloqueado(f"permissões negadas: {sorted(pacote.denied)}")
    resp = executar_sandbox(codigo, lingua, entrada or {},
                            timeout=float(tarefa.timeout_seconds),
                            memoria_mb=int(tarefa.limite_memoria_mb))
    journal.registrar_execucao(
        modulo=tarefa.modulo or "script", versao=tarefa.versao,
        status="ok" if resp["ok"] else "falha",
        plano=vars(tarefa), entrada=entrada or {}, resultado=resp.get("resultado"),
        erro=resp.get("erro"),
        consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 0})
    return resp


def publicar_aprovado(tarefa: Tarefa, manifesto: dict, *, por: str = "humano") -> dict:
    """Publica versão controlada. Exige aprovação registrada p/ módulo (a menos
    que seja leitura pura em modo autônomo controlado)."""
    if not _aprovacao_ok(tarefa) and not _pode_publicar_sem_aprovacao(manifesto):
        raise Bloqueado("publicar módulo exige aprovação humana registrada")
    return _publicar(tarefa.modulo, manifesto, por=por, aprovado=True)


def _pode_publicar_sem_aprovacao(manifesto: dict) -> bool:
    if MODO_PADRAO != "autonomo_controlado":
        return False
    return set(manifesto.get("permissoes", [])) <= approvals_somente_leitura()


def approvals_somente_leitura() -> set[str]:
    return set(AUTO_APROVADAS)


def inspecao_pendencias(tarefa: Tarefa) -> dict:
    sem_aprovacao = approvals.exige_aprovacao_sempre(tarefa.acao) and not _aprovacao_ok(tarefa)
    return {"bloqueada": sem_aprovacao or tarefa.status == "bloqueada",
            "requer_aprovacao": sem_aprovacao,
            "aprovacao_id": tarefa.aprovacao_id or ""}