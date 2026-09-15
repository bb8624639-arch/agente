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


def _executar_criar_modulo(pedido: str) -> dict:
    """Autoexpansão por script, com supervisão (pedido → rascunho aprovável)."""
    from .gerador import gerar_modulo

    r = gerar_modulo(pedido)
    if not r.get("ok"):
        return {"ok": False, "erro": r.get("erro", "falha ao gerar módulo"),
                "status": "falha"}
    ap_id = r.get("ap_id") or ""
    msg = (f"📦 *Módulo gerado:* `{r['nome']}` v{r['versao']}\n"
           f"Arquivo: `{r['caminho']}`\n"
           f"Teste em sandbox: {'✅ passou' if r['teste'] is True else r['teste']}\n"
           f"_Aguardando sua aprovação para publicar._\n"
           f"Para aprovar: `/aprovado {ap_id}`" if ap_id else
           f"📦 *Módulo gerado:* `{r['nome']}` v{r['versao']}\n"
           f"Arquivo: `{r['caminho']}`\n"
           f"Teste em sandbox: {'✅ passou' if r['teste'] is True else r['teste']}\n"
           f"_Aguardando sua aprovação._")
    return {"ok": True, "resultado": r, "status": "aprovacao",
            "resposta_curta": msg}


def _executar_pesquisa(pedido: str) -> dict:
    """Pesquisa na internet sem URL prévia (DuckDuckGo) e abre páginas permitidas.

    Se o pedido já contém uma URL explícita, delega para `_executar_leitura`
    (que continua aplicando a allowlist — um site fora dela permanece bloqueado
    mesmo em modo autônomo).
    """
    from ..browser.allowed import extrair_urls_de
    if extrair_urls_de(pedido):
        plano = {"ferramentas": ["browser/reader"]}
        return _executar_leitura(plano, pedido)

    from ..browser.search import buscar_web, ErroBusca
    # extrai o termo de busca (remove palavras de comando)
    termo = _extrair_termo_busca(pedido)
    try:
        dados = buscar_web(termo, limite=5)
    except ErroBusca as exc:
        return {"ok": False, "erro": str(exc), "status": "falha"}
    if "erro" in dados:
        return {"ok": False, "erro": dados["erro"], "status": "falha"}
    if dados.get("simulado"):
        return {"ok": True, "resultado": dados, "status": "ok",
                "resposta_curta": "🔍 _Modo teste_: nenhuma busca real executada."}
    resultados = dados.get("resultados", [])
    if not resultados:
        return {"ok": True, "resultado": dados, "status": "ok",
                "resposta_curta": "🔍 Nenhum resultado encontrado."}
    linhas = [f"🔍 *{termo}*"] + [
        f"{i+1}. {r['titulo']}\n`{r['url']}`"
        for i, r in enumerate(resultados[:5])]
    linhas.append("\n_Uma página é aberta se o domínio estiver autorizado. "
                  "Para abrir, autorize o domínio com /autorizar <site>_")
    curt = "🔍 **Pesquisa:**\n" + "\n".join(linhas)
    # abre também a primeira página permitida para leitura do trecho
    pagina_aberta = ""
    for r in resultados:
        try:
            from ..browser.allowed import verificar_autorizada, SiteNaoAutorizado
            verificar_autorizada(r["url"])
        except SiteNaoAutorizado:
            continue
        from ..browser.reader import PedidoLeitura, ler_pagina_autorizada, ErroLeitura
        try:
            p = ler_pagina_autorizada(PedidoLeitura(url=r["url"]))
            if p.get("dados_extraidos"):
                pagina_aberta = "\n📄 *Trecho de " + r["url"] + ":*\n" + p["dados_extraidos"][0][:800]
                break
        except (ErroLeitura, Exception):
            continue
    return {"ok": True, "resultado": dados, "status": "ok",
            "resposta_curta": (curt + pagina_aberta) or curt}


def _extrair_termo_busca(pedido: str) -> str:
    import re
    # remove prefixos de comando comuns
    for prefixo in ("pesquise ", "pesquisar ", "busque ", "buscar ",
                    "procure ", "procurar ", "o que é ", "o que sao ",
                    "explique ", "resuma ", "aprenda sobre "):
        if pedido.lower().startswith(prefixo):
            return pedido[len(prefixo):].strip() or pedido
    return pedido.strip() or pedido


def _executar_pensar(pedido: str) -> dict:
    """Capacidade de raciocínio: sintetiza conhecimento e agrega contexto."""
    from ..core.memory import pensar
    pergunta = _extrair_termo_busca(pedido)
    r = pensar(pergunta)
    return {"ok": True, "resultado": r, "status": "ok",
            "resposta_curta": r.get("texto_resposta", "🧠 Pensei, mas não tenho nada ainda.")}


def _executar_contexto(texto: str) -> dict:
    """Importa texto colado longo como conhecimento (rascunho p/ aprovação)."""
    from ..core import knowledge
    texto = texto.strip()
    if len(texto) < 100:
        return {"ok": False, "erro": "texto muito curto para ser contexto",
                "status": "desambiguacao"}
    topico = "contexto_colado: " + (texto[:120].replace("\n", " ")[:80])
    try:
        id_c = knowledge.registrar(topico, texto, origem="usuario",
                                   fonte="telegram_colado")
    except ValueError as exc:
        return {"ok": False, "erro": str(exc), "status": "falha"}
    return {"ok": True, "resultado": {"id": id_c},
            "status": "ok",
            "resposta_curta": (f"📥 *Contexto importado* (#{id_c}) — {len(texto)} caracteres.\n"
                               f"_Aguardando sua aprovação: /aprovar_conh {id_c}")}


def _executar_aprendizado_autonomo(pedido: str) -> dict:
    """Auto-aprendizado determinístico: escolhe trilha e aprende sem aprovação.

    Se o pedido indica um tema (ex.: "aprenda python"), prioriza esse tema;
    caso contrário escolhe o próximo tópico das trilhas (linguagens/web/mobile).
    """
    from ..core import aprendizado_auto
    termo = _extrair_termo_busca(pedido).strip()
    # remove verbos de comando para identificar o tema
    for prefixo in ("aprende", "aprenda", "aprenda sobre", "estude", "estudar",
                    "aprender", "aprendizado", "sobre"):
        if termo.lower().startswith(prefixo):
            termo = termo[len(prefixo):].strip()
            break

    try:
        if termo:
            r = aprendizado_auto.aprender_topico(termo)
            resultado = {"topico": termo, "aprendido": r.get("auto", False),
                         "id": r.get("id"), "conteudo": r.get("conteudo", "")[:200],
                         "fonte": r.get("fonte", "")}
            return {"ok": True, "resultado": resultado, "status": "ok",
                    "resposta_curta": (f"🧠 *Aprendi automaticamente:* {termo}\n"
                                       f"_Aprovado_ (técnico/público)" if r.get("auto")
                                       else f"🧠 *Aprendi:* {termo}\n_Como rascunho p/ aprovação: /aprovar_conh {r['id']}_")}
        # sem tema → ciclo completo de trilhas
        ciclo = aprendizado_auto.ciclo_aprendizado(limite_topicos=2)
        if ciclo.get("simulado"):
            return {"ok": True, "resultado": ciclo, "status": "ok",
                    "resposta_curta": "🧠 _Modo teste: ciclo de aprendizado simulado._"}
        return {"ok": True, "resultado": ciclo, "status": "ok",
                "resposta_curta": ciclo.get("resumo", "🧠 Nada novo no ciclo.")}
    except Exception as exc:
        return {"ok": False, "erro": f"aprendizado autônomo falhou: {exc}",
                "status": "falha"}


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
    # texto longo colado (multi-linha, pouco comando) → força categoria contexto
    if len(pedido.strip()) >= 300 and "\n" in pedido:
        from .classifier import Classificacao
        classificacao = Classificacao("contexto", "ler", 0.99, "texto_colado_long")
    else:
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
        # criar_modulo gera um rascunho local e cria UMA aprovação corporativa
        # para publicar (dentro de _executar_criar_modulo). Não bloquear aqui:
        # a aprovação da publicação acontece após a geração + teste em sandbox.
        if classificacao.categoria != "criar_modulo" and approvals.requer_aprovacao(
                {"acao": classificacao.acao,
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
    elif classificacao.categoria == "criar_modulo":
        resp = _executar_criar_modulo(pedido)
        status = resp.get("status", "ok" if resp["ok"] else "falha")
        erro = resp.get("erro", "")
        resultado = resp
    elif classificacao.categoria in ("pesquisa", "buscar"):
        resp = _executar_pesquisa(pedido)
        status = resp.get("status", "ok" if resp["ok"] else "falha")
        erro = resp.get("erro", "")
        resultado = resp
    elif classificacao.categoria == "pensar":
        resp = _executar_pensar(pedido)
        status = resp.get("status", "ok" if resp["ok"] else "falha")
        erro = resp.get("erro", "")
        resultado = resp
    elif classificacao.categoria == "aprendizado":
        resp = _executar_aprendizado_autonomo(pedido)
        status = resp.get("status", "ok" if resp["ok"] else "falha")
        erro = resp.get("erro", "")
        resultado = resp
    elif classificacao.categoria == "contexto":
        resp = _executar_contexto(pedido)
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