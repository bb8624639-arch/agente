"""Bot Telegram (MVP).

Requisitos:
- token via env `TELEGRAM_BOT_TOKEN`;
- chat autorizado via env `TELEGRAM_CHAT_ID` (ou config) — só ele pode usar;
- recebe pedido → executa pipeline → devolve relatório resumido (11 campos);
- menu com botões (InlineKeyboard) para auto-expansão + comandos de texto
  (`/aprovado <id>`, `/recusar <id>`, `/status`, `/emergencia`, `/menu`).

Sem token: o módulo importa e nada faz (safe).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from ..config import carregar_config, salvar_config
from ..core import approvals, budget, journal
from ..core import knowledge as conhecimento
from ..orchestrator.executor import executar_pedido

# Estado em memória p/ fluxo "aguardando entrada" (tópico do /aprender etc.).
# chave: chat_id; valor: "aprender" | "treinar" | "criar_modulo" | None
_AGUARDANDO: dict = {}

# Carrega .env (raiz do projeto) se existir — credenciais nunca versionadas.
_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV.exists():
    for linha in _ENV.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, _, valor = linha.partition("=")
            os.environ.setdefault(chave.strip(), valor.strip())

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_AUTORIZADO = os.environ.get("TELEGRAM_CHAT_ID", "")

BASE = f"https://api.telegram.org/bot{TOKEN}"


def _url(método: str) -> str:
    return f"{BASE}/{método}"


def _botao(texto: str, dado: str) -> dict:
    return {"text": texto, "callback_data": dado}


def _botao_url(texto: str, url: str) -> dict:
    return {"text": texto, "url": url}


def _teclado_menu() -> list[list[dict]]:
    return [
        [_botao("📚 Aprender da internet", "menu_aprender"),
         _botao("🧠 Ensinar (treinar)", "menu_treinar")],
        [_botao("⚡ Criar módulo/script", "menu_modulo"),
         _botao("📦 Meus módulos", "menu_modulos")],
        [_botao("🗂 Conhecimentos", "menu_conhecimento"),
         _botao("✅ Aprovações", "menu_status")],
        [_botao("🌐 Pesquisar na internet", "menu_pesquisar"),
         _botao("🤔 Pensar", "menu_pensar")],
        [_botao("📥 Contexto colado", "menu_contexto"),
         _botao("💵 Cotação do dólar", "menu_cotacao")],
        [_botao("🆘 Ajuda", "menu_ajuda"),
         _botao("🔁 Recomeçar", "menu_inicio")],
    ]


def _teclado_fixo() -> list[list[str]]:
    """Barra persistente (ReplyKeyboard) — botão de START sempre visível."""
    return [
        ["🏠 /start"],
        ["📚 Aprender", "🧠 Treinar", "🌐 Pesquisar"],
        ["🤔 Pensar", "📥 Contexto", "⚡ Módulo"],
        ["📦 Modulos", "🗂 Conhecimento", "✅ Aprovações"],
        ["💵 Cotação", "🆘 Ajuda"],
    ]


def _enviar_ajuda(chat_id) -> None:
    _enviar(chat_id, _texto_ajuda())


def _texto_ajuda() -> str:
    return ("🧠 *Como usar o agente:*\n\n"
            "• *Aprender* — buscamos um tópico (Wikipedia) e criamos rascunho.\n"
            "• *Pesquisar* — buscamos na internet (DuckDuckGo) e abrimos páginas autorizadas.\n"
            "• *Treinar* — você me ensina (`tópico: conteúdo`).\n"
            "• *Contexto* — cole um texto grande/documento e eu importo como conhecimento.\n"
            "• *Pensar* — eu sintetizo o que aprendi e dou sugestões.\n"
            "• *Módulo* — gero um script, testo e peço aprovação p/ publicar.\n"
            "• *Módulos* — lista módulos registrados.\n"
            "• *Conhecimento* — lista o que aprendi.\n"
            "• *Aprovações* — aprovações pendentes.\n\n"
            "_Comandos diretos:_ /aprender · /pesquisar · /treinar · /contexto · "
            "/pensar · /criar_modulo · /modulos · /conhecimento · /status · /emergencia")


def _enviar(chat_id, texto: str) -> None:
    if not TOKEN:
        return
    payload = {"chat_id": chat_id, "text": texto[:4000], "parse_mode": "Markdown"}
    try:
        resp = requests.post(_url("sendMessage"), json=payload, timeout=15)
        if resp.status_code != 200:
            # fallback: sem parse_mode (emoji/underscore podem quebrar Markdown)
            payload.pop("parse_mode", None)
            resp = requests.post(_url("sendMessage"), json=payload, timeout=15)
            if resp.status_code != 200:
                journal.registrar_diario("erro", f"telegram enviar falhou: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as exc:
        journal.registrar_diario("erro", f"telegram enviar falhou: {exc}")


def _enviar_fixo(chat_id) -> None:
    """Envia barra de botões fixa (ReplyKeyboardMarkup persistente)."""
    if not TOKEN:
        return
    payload = {
        "chat_id": chat_id,
        "text": "🤖 Use o menu abaixo. O botão *🏠 /start* está sempre visível:",
        "reply_markup": {
            "keyboard": _teclado_fixo(),
            "resize_keyboard": True,
            "one_time_keyboard": False,
            "input_field_placeholder": "Me envie um comando ou toque nos botões…",
        },
    }
    try:
        requests.post(_url("sendMessage"), json=payload, timeout=15)
    except requests.RequestException:
        pass


def _enviar_menu(chat_id) -> None:
    _enviar_fixo(chat_id)
    _enviar_teclado(chat_id,
                    "🤖 *Agente Orquestrador* — Auto-expansão com supervisão\n\n"
                    "Escolha uma ação no menu:",
                    _teclado_menu())


def _enviar_teclado(chat_id, texto: str, teclado) -> None:
    if not TOKEN:
        return
    payload = {"chat_id": chat_id, "text": texto[:4000],
               "parse_mode": "Markdown", "reply_markup": {"inline_keyboard": teclado}}
    try:
        resp = requests.post(_url("sendMessage"), json=payload, timeout=15)
        if resp.status_code != 200:
            payload.pop("parse_mode", None)
            resp = requests.post(_url("sendMessage"), json=payload, timeout=15)
            if resp.status_code != 200:
                journal.registrar_diario("erro", f"telegram teclado falhou: {resp.status_code} {resp.text[:200]}")
    except requests.RequestException as exc:
        journal.registrar_diario("erro", f"telegram teclado falhou: {exc}")


def _resumo_relatorio(rel: dict) -> str:
    campos = [
        ("Objetivo", "1_objetivo_entendido"),
        ("Plano", "2_plano_de_etapas"),
        ("Ferramentas", "4_ferramentas_necessarias"),
        ("Permissões", "5_permissoes_necessarias"),
        ("Consumo", "6_custo_consumo_estimados"),
        ("Riscos", "7_riscos"),
        ("Aprovações", "8_acoes_que_precisam_aprovacao"),
        ("Testes", "9_resultado_dos_testes"),
        ("Próximo", "10_proxima_acao_recomendada"),
    ]
    linhas = []
    for nome, chave in campos:
        valor = rel.get(chave)
        if valor or valor == "nenhuma":
            linhas.append(f"*{nome}:* {valor}")
    status = rel.get("11_relatorio_de_execucao", {}).get("status", "")
    linhas.append(f"*Status:* {status}")
    return "\n".join(linhas)


def _autoriza_chat(chat_id: str) -> bool:
    # Se TELEGRAM_CHAT_ID não definido, lê do config; se nenhum, bloqueia.
    cfg = carregar_config()
    autorizado = CHAT_AUTORIZADO or cfg.chat_autorizado_telegram
    return bool(autorizado) and str(chat_id) == str(autorizado)


def _handle(corpo: dict) -> None:
    # Clique em botão do menu (callback_query)
    if corpo.get("callback_query"):
        _handle_callback(corpo)
        return

    mensagem = (corpo.get("message") or {}).get("text", "")
    chat = (corpo.get("message") or {}).get("chat", {})
    chat_id = chat.get("id")
    if not mensagem or chat_id is None:
        return
    if not _autoriza_chat(chat_id):
        _enviar(chat_id, "Não autorizado. Configure TELEGRAM_CHAT_ID.")
        return

    texto = mensagem.strip()
    if texto.startswith("/"):
        comando, _, restante = texto[1:].partition(" ")
        if comando == "aprovado":
            if restante:
                linha = approvals.decidir(restante, True, por="telegram")
                _enviar(chat_id, f"Aprovação {restante}: {linha['status']}" if linha else "id inválido")
        elif comando == "recusar":
            if restante:
                linha = approvals.decidir(restante, False, por="telegram")
                _enviar(chat_id, f"Aprovação {restante}: {linha['status']}" if linha else "id inválido")
        elif comando == "aprovar_conh" or comando == "aprovarconh":
            if restante:
                resultado = conhecimento.decidir(int(restante), True, por="telegram")
                _enviar(chat_id, f"Conhecimento #{restante}: {resultado['status']}" if resultado.get("status") != "inexistente" else "id inexistente")
        elif comando == "rejeitar_conh" or comando == "rejeitarconh":
            if restante:
                resultado = conhecimento.decidir(int(restante), False, por="telegram")
                _enviar(chat_id, f"Conhecimento #{restante}: {resultado['status']}" if resultado.get("status") != "inexistente" else "id inexistente")
        elif comando == "conhecimento":
            _listar_conhecimentos(chat_id)
        elif comando == "treinar":
            if not restante or ":" not in restante:
                _enviar(chat_id, "Uso: /treinar tópico: conteúdo")
                return
            topico, _, conteudo = restante.partition(":")
            try:
                id_criado = conhecimento.registrar(topico, conteudo, origem="usuario")
                _enviar(chat_id, f"✅ Ensinado! Conhecimento #{id_criado} aprovado (origem: você).")
            except ValueError as exc:
                _enviar(chat_id, f"Erro: {exc}")
        elif comando == "aprender":
            if not restante:
                _enviar(chat_id, "Uso: /aprender tópico (ex.: /aprender automação comercial)")
                return
            _enviar(chat_id, f"🔎 Pesquisando '{restante}' na internet...")
            resultado = conhecimento.aprender_e_registrar(restante)
            if "erro" in resultado:
                _enviar(chat_id, f"❌ {resultado['erro']}")
            else:
                _enviar(chat_id,
                        f"📚 *Aprendizado # {resultado['id']}*\n"
                        f"*Tópico:* {resultado['topico']}\n"
                        f"*Fonte:* {resultado['fonte']}\n"
                        f"*Resumo:* {resultado['conteudo']}\n\n"
                        f"{resultado['aviso']}")
        elif comando in ("pesquisar", "pesquisa", "buscar"):
            if not restante:
                _enviar(chat_id, "Uso: /pesquisar <termo> (ex.: /pesquisar IA em vendas)")
                return
            _enviar(chat_id, f"🌐 Buscando '{restante}' na internet...")
            r = executar_pedido(f"pesquise {restante}")
            curt = r.get("relatorio", {}).get("0_resposta_curta", "")
            _enviar(chat_id, curt or "❌ Não consegui pesquisar.")
        elif comando == "pensar":
            if restante:
                _enviar(chat_id, "🤔 Pensando...")
                r = executar_pedido(f"pense sobre {restante}")
            else:
                _enviar(chat_id, "🤔 Sintetizando o que aprendi...")
                r = executar_pedido("pensar")
            curt = r.get("relatorio", {}).get("0_resposta_curta", "")
            _enviar(chat_id, curt or "🧠 Pensei, mas não tenho nada ainda.")
        elif comando == "contexto":
            if not restante:
                _enviar(chat_id, "Cole o texto/documento agora (ou use /contexto <texto>). Quero que importe tudo:")
                _AGUARDANDO[str(chat_id)] = "contexto"
                return
            r = _importar_contexto(restante)
            _enviar(chat_id, r["resposta_curta"] if r.get("resposta_curta") else str(r))
        elif comando in ("aprovar", "aprovar_conh", "aprovarconh"):
            if restante:
                try:
                    resultado = conhecimento.decidir(int(restante), True, por="telegram")
                    _enviar(chat_id, f"Conhecimento #{restante}: {resultado['status']}" if resultado.get("status") != "inexistente" else "id inexistente")
                except ValueError:
                    _enviar(chat_id, "Use: /aprovar <id> de um conhecimento")
        elif comando in ("criar_modulo", "criarmodulo") or comando == "modulo":
            if not restante:
                _enviar(chat_id, "Uso: /criar_modulo <descrição> (ex.: /criar_modulo script que valida CPF)")
                return
            resposta_nova = executar_pedido(f"crie um {restante}")
            curt = resposta_nova["relatorio"].get("0_resposta_curta", "")
            _enviar(chat_id, curt or resposta_nova["relatorio"]["11_relatorio_de_execucao"]["status"])
        elif comando == "modulos" or comando == "listar_modulos":
            _listar_modulos(chat_id)
        elif comando == "menu" or comando == "inicio":
            _enviar_menu(chat_id)
        elif comando == "start" or comando == "help":
            _enviar_menu(chat_id)
        elif comando == "status":
            _status(chat_id)
        elif comando == "emergencia":
            cfg = carregar_config()
            cfg.emergencia = True
            salvar_config(cfg)
            _enviar(chat_id, "🔴 Emergência acionada. Execuções pausadas.")
        else:
            _enviar(chat_id, f"Comando desconhecido: /{comando}")
        return

    # Texto livre: fluxo de aguardando do menu ou execução direta
    _processar_texto(chat_id, texto)


def _resolver_callback(chat_id, dado: str) -> bool:
    """Processa os cliques do InlineKeyboard. Devolve True se identificado."""
    if not dado.startswith("menu_"):
        return False
    _, acao = dado.split("_", 1)

    if acao == "inicio" or acao == "ajuda":
        _enviar_menu(chat_id)
        if acao == "ajuda":
            _enviar(chat_id, _texto_ajuda())
        return True
    if acao == "aprender":
        _AGUARDANDO[str(chat_id)] = "aprender"
        _enviar(chat_id,
                "📚 *Aprender da internet*\n\n"
                "Envie o tópico que você quer que eu aprenda.\n"
                "_Ex.: automação comercial, marketing digital, inteligência artificial_")
        return True
    if acao == "treinar":
        _AGUARDANDO[str(chat_id)] = "treinar"
        _enviar(chat_id,
                "🧠 *Ensinar (treinar)*\n\n"
                "Envie no formato `tópico: conteúdo`.\n"
                "_Ex.: preferências do cliente: nosso maior cliente prefere "
                "WhatsApp pela manhã_")
        return True
    if acao == "pesquisar":
        _AGUARDANDO[str(chat_id)] = "pesquisar"
        _enviar(chat_id,
                "🌐 *Pesquisar na internet*\n\n"
                "Envie o termo para eu buscar (DuckDuckGo).\n"
                "_Ex.: tendências de automação comercial_")
        return True
    if acao == "pensar":
        _AGUARDANDO[str(chat_id)] = "pensar"
        _enviar(chat_id,
                "🤔 *Pensar*\n\n"
                "Envie a pergunta (opcional), ou apenas *ok* para eu sintetizar "
                "tudo o que sei e sugerir próximos passos.")
        return True
    if acao == "contexto":
        _AGUARDANDO[str(chat_id)] = "contexto"
        _enviar(chat_id,
                "📥 *Contexto colado*\n\n"
                "Cole aqui o texto/documento inteiro (posso ler até 30 mil "
                "caracteres) e eu importo como conhecimento para você aprovar.")
        return True
    if acao == "modulo":
        _AGUARDANDO[str(chat_id)] = "criar_modulo"
        _enviar(chat_id,
                "⚡ *Criar módulo/script*\n\n"
                "Descreva o que o script deve fazer.\n"
                "_Ex.: script que valida CPF, script que calcula IMC, "
                "script que dobra um número_")
        return True
    if acao == "modulos":
        _listar_modulos(chat_id)
        return True
    if acao == "conhecimento":
        _listar_conhecimentos(chat_id)
        return True
    if acao == "status":
        _status(chat_id)
        return True
    if acao == "cotacao":
        _enviar(chat_id, "🔎 Consultando PTAX no Banco Central...")
        resposta = executar_pedido("qual a cotação do dólar hoje?")
        curt = resposta["relatorio"].get("0_resposta_curta", "")
        _enviar(chat_id, curt or _resumo_relatorio(resposta["relatorio"]))
        return True
    return True


def _listar_modulos(chat_id) -> None:
    from ..core import persistence
    linhas = persistence.consultar(
        "SELECT nome, versao, perfil, aprovado FROM modulos "
        "WHERE status='ativo' ORDER BY nome, versao", ())
    if not linhas:
        _enviar(chat_id, "📦 Nenhum módulo ainda. Use *Criar módulo/script* no menu para gerar o primeiro.")
        return
    texto_mod = "*Meus módulos:*\n" + "\n".join(
        f"`{l['nome']}` v{l['versao']} ({l['perfil']} {'✅' if l['aprovado'] else '⏳'})"
        for l in linhas[-15:])
    _enviar(chat_id, texto_mod)


def _listar_conhecimentos(chat_id) -> None:
    lista = conhecimento.listar("rascunho") + conhecimento.listar("aprovado")
    if not lista:
        _enviar(chat_id, "🗂 Nenhum conhecimento ainda. Use *Aprender da internet* ou *Ensinar* no menu.")
        return
    linhas = []
    for k in lista[:10]:
        estado = "✅" if k["status"] == "aprovado" else ("⏳" if k["status"] == "rascunho" else "❌")
        linhas.append(f"{estado} #{k['id']} {k['topico']} ({k['status']})")
    _enviar(chat_id, "*Conhecimentos:*\n" + "\n".join(linhas))


def _status(chat_id) -> None:
    linhas_status = []
    pend = approvals.pendentes()
    if pend:
        linhas_status.append("*Aprovações pendentes:*")
        for p in pend[:8]:
            linhas_status.append(f"`{p['id']}` {p['acao']} ({p['modulo']})")
        linhas_status.append("→ Aprove com /aprovado <id> ou /recusar <id>")
    else:
        linhas_status.append("✅ *Nenhuma aprovação pendente.*")
    pend_conh = conhecimento.listar("rascunho")
    if pend_conh:
        linhas_status.append("")
        linhas_status.append("*Conhecimentos aguardando você:*")
        for k in pend_conh[:5]:
            linhas_status.append(f"#{k['id']} {k['topico']} (/aprovar_conh {k['id']})")
    # estatísticas rápidas
    try:
        from ..core.memory import estatisticas
        est = estatisticas()
        linhas_status.append("")
        linhas_status.append("*Resumo do agente:*")
        linhas_status.append(f"· Conhecimento: aprovados={est['conhecimento'].get('aprovado', 0)} "
                             f"rascunhos={est['conhecimento'].get('rascunho', 0)}")
        linhas_status.append(f"· Módulos: publicados={est['modulos'].get('publicado', 0)} "
                             f"rascunhos={est['modulos'].get('rascunho', 0)}")
        linhas_status.append(f"· Erros recentes: {est['erros_recentes']}")
    except Exception:
        pass
    _enviar(chat_id, "\n".join(linhas_status))


def _processar_texto(chat_id, texto: str) -> None:
    """Fluxo de texto livre: se aguardando entrada do menu, trata; senão executar."""
    espera = _AGUARDANDO.pop(str(chat_id), None)
    if not espera:
        # botões da barra fixa chegam como texto — mapear para ações
        if _mapear_botao_fixo(chat_id, texto):
            return
        # texto colado longo (ex.: documento inteiro) → importa como contexto
        if len(texto.strip()) >= 300 and "\n" in texto:
            _enviar(chat_id, "📥 Detectei um texto longo/colado. Importando como contexto...")
            r = _importar_contexto(texto)
            _enviar(chat_id, r["resposta_curta"] if r.get("resposta_curta") else str(r))
            return
        # se o texto parecer um comando de aprendizado (aprender/pesquisar/pensar)
        _executar_pedido_chat(chat_id, texto)
        return
    if espera == "aprender":
        _enviar(chat_id, f"🔎 Pesquisando '{texto}' na internet...")
        resultado = conhecimento.aprender_e_registrar(texto)
        if "erro" in resultado:
            _enviar(chat_id, f"❌ {resultado['erro']}")
        else:
            _enviar(chat_id,
                    f"📚 *Aprendizado # {resultado['id']}*\n"
                    f"*Tópico:* {resultado['topico']}\n"
                    f"*Fonte:* {resultado['fonte']}\n"
                    f"*Resumo:* {resultado['conteudo']}\n\n"
                    f"{resultado['aviso']}\n\n"
                    f"Para aprovar: `/aprovar_conh {resultado['id']}`")
    elif espera == "treinar":
        if ":" not in texto:
            _enviar(chat_id, "Formato: `tópico: conteúdo`. Ex.: `preferências: cliente gosta de e-mail`")
            _AGUARDANDO[str(chat_id)] = "treinar"
            return
        topico, _, conteudo = texto.partition(":")
        try:
            id_c = conhecimento.registrar(topico, conteudo, origem="usuario")
            _enviar(chat_id, f"✅ Ensinado! Conhecimento #{id_c} aprovado (origem: você).")
        except ValueError as exc:
            _enviar(chat_id, f"Erro: {exc}")
    elif espera == "criar_modulo":
        resposta_nova = executar_pedido(f"crie um {texto}")
        curt = resposta_nova["relatorio"].get("0_resposta_curta", "")
        _enviar(chat_id, curt or _resumo_relatorio(resposta_nova["relatorio"]))
    elif espera == "pesquisar":
        _enviar(chat_id, f"🌐 Buscando '{texto}' na internet...")
        r = executar_pedido(f"pesquise {texto}")
        curt = r.get("relatorio", {}).get("0_resposta_curta", "")
        _enviar(chat_id, curt or "❌ Não consegui pesquisar.")
    elif espera == "pensar":
        _enviar(chat_id, "🤔 Pensando...")
        r = executar_pedido(f"pense sobre {texto}")
        curt = r.get("relatorio", {}).get("0_resposta_curta", "")
        _enviar(chat_id, curt or "🧠 Pensei, mas não tenho nada ainda.")
    elif espera == "contexto":
        r = _importar_contexto(texto)
        _enviar(chat_id, r["resposta_curta"] if r.get("resposta_curta") else str(r))


def _importar_contexto(texto: str) -> dict:
    """Importa texto colado como conhecimento (rascunho p/ aprovação)."""
    from ..core import knowledge as k
    texto = texto.strip()
    if len(texto) < 50:
        return {"resposta_curta": "Texto muito curto. Cole um documento/pasta com contexto."}
    topico = "contexto_colado:" + (texto.replace("\n", " ")[:120])
    try:
        id_c = k.registrar(topico, texto[:30000], origem="usuario", fonte="telegram")
    except ValueError as exc:
        return {"resposta_curta": f"Erro: {exc}"}
    return {"resposta_curta":
            f"📥 *Contexto importado* (#{id_c}) — {len(texto)} caracteres.\n"
            f"_Aguardando aprovação: /aprovar_conh {id_c}_"}


def _mapear_botao_fixo(chat_id, texto: str) -> bool:
    """Mapeia os textos da barra fixa (ReplyKeyboard) para ações do menu.

    Quando o usuário toca num botão da ReplyKeyboard, ele envia *texto*.
    Aqui traduzimos para o mesmo efeito dos botões inline.
    """
    texto_norm = texto.strip().lower()
    mapa = {
        "🏠 /start": "inicio", "/start": "inicio", "🏠": "inicio",
        "📚 aprender": "aprender", "aprender": "aprender",
        "🧠 treinar": "treinar", "treinar": "treinar",
        "🌐 pesquisar": "pesquisar", "pesquisar": "pesquisar",
        "🤔 pensar": "pensar", "pensar": "pensar",
        "📥 contexto": "contexto", "contexto": "contexto",
        "⚡ módulo": "modulo", "módulo": "modulo", "modulo": "modulo",
        "📦 modulos": "modulos", "módulos": "modulos", "módulos": "modulos",
        "🗂 conhecimento": "conhecimento", "conhecimento": "conhecimento",
        "✅ aprovações": "status", "aprovações": "status", "aprovações": "status",
        "💵 cotação": "cotacao", "cotação": "cotacao", "cotacao": "cotacao",
        "🆘 ajuda": "ajuda", "ajuda": "ajuda",
    }
    acao = mapa.get(texto_norm)
    if not acao:
        return False
    # "modulo" e "modulos"/"conhecimento"/"status"/"cotacao" são resolvidos direto;
    # os demais entram em fluxo aguardando.
    _resolver_callback_publico(chat_id, acao)
    return True


def _resolver_callback_publico(chat_id, acao: str) -> bool:
    """Trata acao do menu pelo nome (sem prefixo menu_), para botões fixos."""
    return _resolver_callback(chat_id, f"menu_{acao}")


def _executar_pedido_chat(chat_id, texto: str) -> None:
    resposta = executar_pedido(texto)
    resposta_curta = resposta["relatorio"].get("0_resposta_curta", "")
    if resposta_curta:
        _enviar(chat_id, resposta_curta)
    else:
        _enviar(chat_id, _resumo_relatorio(resposta["relatorio"]))
    if resposta.get("handoff"):
        _enviar(chat_id, f"Transferência: {resposta['handoff']}")


def _handle_callback(corpo: dict) -> None:
    """Processa cliques em botões do InlineKeyboard."""
    callback = corpo.get("callback_query") or {}
    mensagem = callback.get("message") or {}
    chat_id = (mensagem.get("chat") or {}).get("id")
    dado = callback.get("data", "")
    if chat_id is None or not _autoriza_chat(chat_id):
        return
    _resolver_callback(chat_id, dado)
    # responde ao callback para sumir o "carregando..."
    if callback.get("id") and TOKEN:
        try:
            requests.post(_url("answerCallbackQuery"),
                          json={"callback_query_id": callback["id"]}, timeout=10)
        except requests.RequestException:
            pass


def rodar_polling(intervalo_s: float = 2.0) -> None:
    """Loop de polling simples. Economia: intervalo configurável, sem IA aqui.

    No início, registra o botão fixo (setMyCommands) e o menu de botões.
    """
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN não definido; Telegram desabilitado.")
        return
    _registrar_comandos()
    offset = 0
    print("Telegram bot iniciado (polling). Ctrl+C para sair.")
    while True:
        try:
            resp = requests.get(
                _url("getUpdates"),
                params={"timeout": 20, "offset": offset}, timeout=30)
            dados = resp.json()
            for update in dados.get("result", []):
                offset = update["update_id"] + 1
                _handle(update)
        except requests.RequestException as exc:
            journal.registrar_diario("erro", f"telegram polling: {exc}")
            time.sleep(3)
        except KeyboardInterrupt:
            break


def _registrar_comandos() -> None:
    """Expõe os comandos no campo de texto do Telegram (BotFather automático)."""
    if not TOKEN:
        return
    comandos = [
        {"command": "start", "description": "Iniciar / menu principal"},
        {"command": "menu", "description": "Abrir menu de botões"},
        {"command": "aprender", "description": "Aprender um tópico da internet"},
        {"command": "pesquisar", "description": "Pesquisar na internet (DuckDuckGo)"},
        {"command": "treinar", "description": "Ensinar tópico: conteúdo"},
        {"command": "contexto", "description": "Importar texto colado como conhecimento"},
        {"command": "pensar", "description": "Sintetizar o que aprendi / responder"},
        {"command": "criar_modulo", "description": "Gerar script e pedir aprovação"},
        {"command": "aprovado", "description": "Aprovar módulo ou aprovação por id"},
        {"command": "aprovar_conh", "description": "Aprovar conhecimento por id"},
        {"command": "rejeitar_conh", "description": "Rejeitar conhecimento por id"},
        {"command": "modulos", "description": "Listar módulos"},
        {"command": "conhecimento", "description": "Listar conhecimentos"},
        {"command": "cotacao", "description": "Cotação do dólar (PTAX)"},
        {"command": "status", "description": "Ver aprovações e resumo"},
        {"command": "emergencia", "description": "Pausar tudo"},
    ]
    try:
        requests.post(_url("setMyCommands"),
                      json={"commands": comandos}, timeout=15)
    except requests.RequestException:
        pass


if __name__ == "__main__":
    rodar_polling()