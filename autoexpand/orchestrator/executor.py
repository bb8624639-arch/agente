"""Executor do orquestrador: pedido → classificação → plano → execução → relatório.

Pipeline descrito pelo usuário (item 16 do MVP):
  a. receber solicitação em linguagem natural
  b. classificar por regras antes de usar IA
  c. gerar plano de execução
  d. validar ferramentas e permissões
  e. executar tarefa de leitura em site autorizado
  f. registrar a execução
  g. calcular consumo estimado
  h. retornar resultado
  i. gerar relatório/handoff
  j. bloquear ação sensível sem aprovação

Não usa LLM por padrão: o roteador econômico decide se um passo precisa
de modelo (e só chama se AE_LLM_* estiver configurado).
"""

from __future__ import annotations

import datetime as dt

from ..config import carregar_config, MODO_PADRAO
from ..core import approvals, budget, journal
from ..core.execution import Bloqueado, Tarefa
from .classifier import classificar
from .planner import planejar
from .report import montar_relatorio, montar_handoff, salvar_handoff


def _executar_cotacao() -> dict:
    from ..connectors.exchange import cotacao_dolar_hoje, formatar_cotacao

    cot = cotacao_dolar_hoje()
    if "erro" in cot:
        dados = {"compra": None, "venda": None, "fonte": "PTAX/BCB",
                 "erro": cot["erro"]}
        journal.registrar_execucao(modulo="connectors/exchange", status="falha",
                                   plano=None, resultado=dados, erro=cot["erro"])
        return {"ok": False, "erro": cot["erro"], "status": "falha"}
    journal.registrar_execucao(modulo="connectors/exchange", status="ok",
                               plano=None, resultado=cot)
    return {"ok": True, "resultado": cot, "status": "ok",
            "resposta_curta": formatar_cotacao(cot)}


def _executar_leitura(plano: dict, pedido: str) -> dict:
    from ..browser.allowed import extrair_urls_de
    from ..browser.reader import PedidoLeitura, ler_pagina_autorizada, ErroLeitura

    urls = extrair_urls_de(pedido)
    if not urls:
        # Sem URL explícita: usa o primeiro domínio autorizado? Não. Devolve
        # "não sei" honesto: não inventamos URL.
        return {"ok": False, "erro": "nenhuma URL identificada no pedido; "
                                     "informe uma URL autorizada", "status": "desambiguacao"}
    from ..browser.allowed import SiteNaoAutorizado
    try:
        resultado = ler_pagina_autorizada(PedidoLeitura(url=urls[0]))
    except SiteNaoAutorizado as exc:
        # site fora da allowlist: falha de autorização (nunca auto-adicionar)
        return {"ok": False, "erro": f"site não autorizado: {exc.url}",
                "status": "bloqueada"}
    except ErroLeitura as exc:
        return {"ok": False, "erro": str(exc), "status": "falha"}
    return {"ok": True, "resultado": resultado, "status": "ok"}


def executar_pedido(pedido: str, *, modo: str | None = None) -> dict:
    """Pipeline completo (b..j). Modo default: config (teste)."""
    cfg = carregar_config()
    if modo is not None:
        cfg.modo = modo
    budget.iniciar_tarefa()
    try:
        return _executar_pipeline(pedido, cfg)
    finally:
        budget.encerrar_tarefa()


def _executar_pipeline(pedido: str, cfg) -> dict:
    # b. classificar por regras (sem IA)
    classificacao = classificar(pedido)
    if classificacao.categoria == "desconhecida":
        plano = planejar(pedido, classificacao)
        rel = montar_relatorio(
            objetivo=pedido, classificacao="desconhecida", plano=plano,
            status="desconhecida", erro="não identificado",
            proxima_acao="desambiguar objetivo",
            testes=[{"regras": True, "llm": False, "motivo": "sem LLM (econômico)"}])
        return {"tipo": "resposta", "relatorio": rel, "handoff": None, "status": "desconhecida"}

    # c. plano
    plano = planejar(pedido, classificacao)
    if plano.get("status") == "precisa_desambiguacao":
        rel = montar_relatorio(
            objetivo=pedido, classificacao=classificacao.categoria, plano=plano,
            status="desconhecida", erro="ambiguidade",
            proxima_acao="responder perguntas de desambiguação")
        return {"tipo": "resposta", "relatorio": rel, "handoff": None, "status": "desconhecida"}

    # j. bloquear ação sensível sem aprovação
    aprov_pend: list[dict] = []
    tarefa = Tarefa(
        objetivo=pedido, acao=classificacao.acao,
        modulo=(plano.get("ferramentas") or ["desconhecido"])[0],
        efeito_externo=plano.get("aprovacao_necessaria", False),
        permissoes_necessarias=plano.get("permisoes", []),
    )
    try:
        if approvals.requer_aprovacao({"acao": classificacao.acao,
                                       "classe": classificacao.acao,
                                       "efeito_externo": plano.get("aprovacao_necessaria", False)},
                                      modo=cfg.modo):
            ap_id = approvals.criar_aprovacao(classificacao.acao, modulo=tarefa.modulo,
                                              contexto={"objetivo": pedido,
                                                        "comando": cfg.modo})
            aprov_pend.append({"acao": classificacao.acao, "id": ap_id})
            rel = montar_relatorio(
                objetivo=pedido, classificacao=classificacao.categoria, plano=plano,
                status="aprovacao", testes=[{"bloqueado": "sem aprovação humana"}],
                proxima_acao="aguardar aprovação pelo painel/Telegram",
                aprovacoes_pendentes=aprov_pend)
            handoff = montar_handoff(
                objetivo_atual=pedido, etapa="aguardando_aprovacao",
                decisoes=[{"bloqueado": classificacao.acao, "motivo": "ação sensível"}],
                proximo_passo=f"aprovar {ap_id} para liberar execução")
            caminho = salvar_handoff(handoff)
            return {"tipo": "resposta", "relatorio": rel, "handoff": caminho,
                    "status": "aprovacao"}
    except Bloqueado as exc:
        handoff = montar_handoff(
            objetivo_atual=pedido, etapa="bloqueada", erros=[str(exc)],
            decisoes=[{"bloqueado": True, "motivo": str(exc)}],
            proximo_passo="revisar regras/permissões")
        caminho = salvar_handoff(handoff)
        rel = montar_relatorio(objetivo=pedido, classificacao=classificacao.categoria,
                               plano=plano, erro=str(exc), status="bloqueada",
                               proxima_acao="revisar permissões")
        return {"tipo": "resposta", "relatorio": rel, "handoff": caminho, "status": "bloqueada"}

    # e. executar conforme categoria
    resultado, status, erro = {"ok": False}, "falha", ""
    if classificacao.categoria == "cotacao":
        resp = _executar_cotacao()
        status = resp.get("status", "ok" if resp["ok"] else "falha")
        erro = resp.get("erro", "")
        resultado = resp
    elif plano.get("ferramentas") and "browser/reader" in plano["ferramentas"]:
        resp = _executar_leitura(plano, pedido)
        status = resp.get("status", "ok" if resp["ok"] else "falha")
        erro = resp.get("erro", "")
        resultado = resp
    else:
        resultado = {"ok": False, "erro": "adaptador não implementado no MVP"}
        status = "falha"

    # f,g,h. registro + consumo + resultado
    resultado_final = resultado if resultado.get("ok") else {"erro_honesto": resultado.get("erro")}
    consumo = journal.resumo_consumo()
    testes = [{"executado": True, "sandbox": True, "resultado": resultado.get("ok", False)}]
    rel = montar_relatorio(
        objetivo=pedido, classificacao=classificacao.categoria, plano=plano,
        resultado=resultado_final, erro=erro, status=status, testes=testes,
        resposta_curta=resultado.get("resposta_curta", "") if isinstance(resultado, dict) else "",
        proxima_acao="concluído" if status == "ok" else "revisar erro no journal")
    handoff = montar_handoff(
        objetivo_atual=pedido, etapa="executado" if status == "ok" else "falhou",
        decisoes=[{"classificacao": classificacao.categoria, "acao": classificacao.acao}],
        erros=[erro] if erro else [],
        testes=[{"modulo": t.get("modulo") for t in testes}],
        proximo_passo="validar resultado no painel" if status == "ok" else "diagnosticar falha")
    caminho = salvar_handoff(handoff)
    return {"tipo": "resposta", "relatorio": rel, "handoff": caminho, "status": status}