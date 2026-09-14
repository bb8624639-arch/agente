"""Relatório final (formato de 11 itens do usuário) + geração de handoff.

Monta a resposta estruturada que o agente devolve para qualquer solicitação:
  1. Objetivo entendido
  2. Plano de etapas
  3. Agentes envolvidos
  4. Ferramentas necessárias
  5. Permissões necessárias
  6. Custo e consumo estimados
  7. Riscos
  8. Ações que precisam de aprovação
  9. Resultado dos testes
  10. Próxima ação recomendada
  11. Relatório de execução
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..config import MODO_PADRAO, limites_json
from ..core import budget, journal


def montar_relatorio(*, objetivo: str, classificacao: str, plano: dict | None = None,
                     resultado: Any = None, erro: str = "", status: str = "ok",
                     aprovacoes_pendentes: list | None = None,
                     testes: list | None = None,
                     proxima_acao: str = "", agentes: list | None = None,
                     resposta_curta: str = "") -> dict:
    """Devolve relatório no formato de 11 campos exigido pelo usuário."""
    consumo = journal.resumo_consumo()
    aprov_pend = aprovacoes_pendentes if aprovacoes_pendentes is not None else []
    testes = testes or []
    return {
        "formato": "relatorio_11_campos",
        "modo": MODO_PADRAO,
        "0_resposta_curta": resposta_curta,
        "1_objetivo_entendido": objetivo,
        "2_plano_de_etapas": (plano or {}).get("etapas", []),
        "3_agentes_envolvidos": agentes or ["orquestrador"],
        "4_ferramentas_necessarias": (plano or {}).get("ferramentas", []),
        "5_permissoes_necessarias": (plano or {}).get("permisoes", []),
        "6_custo_consumo_estimados": consumo,
        "7_riscos": (plano or {}).get("riscos", []),
        "8_acoes_que_precisam_aprovacao": [
            {"acao": a.get("acao"), "aprovacao_id": a.get("id")}
            for a in aprov_pend
        ] if aprov_pend else (["nenhuma"] if status not in ("aprovacao", "bloqueada") else []),
        "9_resultado_dos_testes": testes or (resultado if status in ("ok",) else []),
        "10_proxima_acao_recomendada": proxima_acao or
            ("desambiguar objetivo" if status == "desconhecida"
             else "aguardar aprovação humana para ações sensíveis" if aprov_pend
             else "concluído"),
        "11_relatorio_de_execucao": {
            "status": status, "erro": erro or None,
            "classificacao": classificacao,
            "limites": limites_json(),
        },
    }


def montar_handoff(*, objetivo_atual: str, etapa: str, decisoes: list | None = None,
                   arquivos: list | None = None, testes: list | None = None,
                   erros: list | None = None, proximo_passo: str,
                   consumo: dict | None = None,
                   instrucao_proximo_agente: str = "") -> dict:
    """Estrutura persistida em state/handoff-<data>.md para continuação sem recomeço.

    Inclui limites de crédito/tempo por execução e caminho de retomada.
    """
    quando = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "gerado_em": quando,
        "etapa": etapa,
        "objetivo_atual": objetivo_atual,
        "decisoes": decisoes or [],
        "arquivos_criados": arquivos or [],
        "testes_executados": testes or [],
        "erros": erros or [],
        "consumo_estimado": consumo or journal.resumo_consumo(),
        "credito_max_por_execucao": "10 chamadas IA · 3 tentativas · 60 s timeout",
        "proximo_passo_exato": proximo_passo,
        "instrucoes_para_continuar_sem_recomecar": (
            instrucao_proximo_agente
            or f"Retomar a partir da etapa '{etapa}'. Estado em SQLite. "
               f"Rodar `pytest -q` antes de continuar. Não recriar arquivos já listados."),
    }


def salvar_handoff(handoff: dict, caminho: str | None = None) -> str:
    """Grava handoff em arquivo .md (path por padrão em state/)."""
    import json
    from pathlib import Path
    from ..config import PASTA_ESTADO

    PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
    if caminho is None:
        nome = f"handoff-{dt.datetime.now():%Y%m%d-%H%M%S}.md"
        caminho = str(PASTA_ESTADO / nome)
    Path(caminho).write_text(
        "# Handoff do Agente Orquestrador\n\n```json\n"
        + json.dumps(handoff, ensure_ascii=False, indent=2)
        + "\n```\n", encoding="utf-8")
    return caminho