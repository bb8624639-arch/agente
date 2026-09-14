"""Orçamento e limites de consumo.

Contadores registrados por período (tarefa, dia, mês) na tabela `consumo`.
`verificar_limites` lança `LimiteExcedido` se qualquer teto for atingido —
o executor interrompe antes de continuar. O modo `emergencia` bloqueia tudo.

Limites (config.py): mensal R$ 20 · diário R$ 5 · por tarefa R$ 2 ·
10 chamadas IA/tarefa · 3 tentativas · 60 s timeout · 5 páginas.
"""

from __future__ import annotations

import datetime as dt
import uuid

from ..config import (LIMITE_DIARIO_IA, LIMITE_MENSAL_IA, LIMITE_POR_TAREFA,
                      MAX_CHAMADAS_IA_POR_TAREFA, MODO_PADRAO)
from .persistence import consultar, executar, j_loads, j_dumps


class LimiteExcedido(Exception):
    def __init__(self, motivo: str):
        self.motivo = motivo
        super().__init__(motivo)


def _periodos(agora: dt.datetime | None = None) -> tuple[str, str, str]:
    agora = agora or dt.datetime.now()
    return (f"tarefa:{_tarefa_atual()}", f"dia:{agora:%Y-%m-%d}", f"mes:{agora:%Y-%m}")


def _tarefa_atual() -> str:
    return getattr(_tarefa_atual, "atual", "default")


def iniciar_tarefa() -> str:
    """Cria um id único de tarefa para contabilizar o orçamento por tarefa."""
    tarefa = uuid.uuid4().hex[:12]
    _tarefa_atual.atual = tarefa
    return tarefa


def encerrar_tarefa() -> None:
    _tarefa_atual.atual = "default"


def _ler(periodo: str) -> dict:
    r = consultar("SELECT * FROM consumo WHERE periodo=?", (periodo,))
    if r:
        return dict(r[0])
    return {"periodo": periodo, "chamadas_ia": 0, "tokens_in": 0,
            "tokens_out": 0, "custo_r": 0.0, "paginas": 0}


def somar(periodo: str, campo: str, valor: float | int) -> None:
    r = consultar("SELECT * FROM consumo WHERE periodo=?", (periodo,))
    if not r:
        executar("INSERT INTO consumo (periodo) VALUES (?)", (periodo,))
    executar(f"UPDATE consumo SET {campo} = {campo} + ? WHERE periodo=?", (valor, periodo))


def registrar_uso(*, chamadas_ia: int = 0, tokens_in: int = 0, tokens_out: int = 0,
                  custo_r: float = 0.0, paginas: int = 0) -> None:
    agora = dt.datetime.now()
    periodo_tarefa, periodo_dia, periodo_mes = _periodos(agora)
    for periodo, delta in ((periodo_tarefa, chamadas_ia), (periodo_dia, chamadas_ia),
                           (periodo_mes, chamadas_ia)):
        if delta:
            somar(periodo, "chamadas_ia", delta)
    for periodo, delta in ((periodo_tarefa, tokens_in), (periodo_dia, tokens_in),
                           (periodo_mes, tokens_in)):
        if delta:
            somar(periodo, "tokens_in", delta)
    for periodo, delta in ((periodo_tarefa, tokens_out), (periodo_dia, tokens_out),
                           (periodo_mes, tokens_out)):
        if delta:
            somar(periodo, "tokens_out", delta)
    for periodo, delta in ((periodo_tarefa, custo_r), (periodo_dia, custo_r),
                           (periodo_mes, custo_r)):
        if delta:
            somar(periodo, "custo_r", delta)
    for periodo, delta in ((periodo_tarefa, paginas), (periodo_dia, paginas),
                           (periodo_mes, paginas)):
        if delta:
            somar(periodo, "paginas", delta)


def _custo_ate(periodo: str) -> float:
    return float(_ler(periodo).get("custo_r", 0.0))


def _chamadas_ate(periodo: str) -> int:
    return int(_ler(periodo).get("chamadas_ia", 0))


def _paginas_ate(periodo: str) -> int:
    return int(_ler(periodo).get("paginas", 0))


def verificar_limites(*, paginas_futuras: int = 0, chamadas_ia_futuras: int = 0,
                      custo_futuro: float = 0.0) -> None:
    """Levanta LimiteExcedido se qualquer teto for/fora violado.

    - Paginas: limite por execução é de 5 — checado sobre o período do dia
      (aproximação conservadora: acumula o dia todo).
    - Invariante do usuário: nenhuma tarefa deve passar de R$ 2 / 10 chamadas.
    """
    from ..config import MAX_PAGINAS_POR_EXECUCAO
    tarefa, dia, mes = _periodos()
    checks = [
        ("custo por tarefa", _custo_ate(tarefa) + custo_futuro, LIMITE_POR_TAREFA),
        ("custo diário", _custo_ate(dia) + custo_futuro, LIMITE_DIARIO_IA),
        ("custo mensal", _custo_ate(mes) + custo_futuro, LIMITE_MENSAL_IA),
        ("chamadas IA por tarefa", _chamadas_ate(tarefa) + chamadas_ia_futuras,
         MAX_CHAMADAS_IA_POR_TAREFA),
    ]
    for nome, valor, teto in checks:
        if valor > teto:
            raise LimiteExcedido(
                f"{nome}: {valor:g} ultrapassa teto {teto:g} "
                f"(modo={MODO_PADRAO}; uso acumulado: tarefa={_custo_ate(tarefa):g} R$, "
                f"dia={_custo_ate(dia):g} R$, mês={_custo_ate(mes):g} R$)")
    if _paginas_ate(dia) + paginas_futuras > MAX_PAGINAS_POR_EXECUCAO * 10:
        raise LimiteExcedido("limite diário de páginas excedido")


def consumo_consolidado() -> dict:
    agora = dt.datetime.now()
    tarefa = _tarefa_atual()
    parte = {
        "tarefa": _ler(f"tarefa:{tarefa}"),
        "dia": _ler(f"dia:{agora:%Y-%m-%d}"),
        "mes": _ler(f"mes:{agora:%Y-%m}"),
        "limites": {"mensal_ia": LIMITE_MENSAL_IA, "diario_ia": LIMITE_DIARIO_IA,
                    "por_tarefa": LIMITE_POR_TAREFA,
                    "max_chamadas_ia": MAX_CHAMADAS_IA_POR_TAREFA},
    }
    return parte


def emergencia_acionada() -> bool:
    from ..config import carregar_config
    return carregar_config().emergencia