"""Bot Telegram opcional (MVP).

Requisitos:
- token via env `TELEGRAM_BOT_TOKEN`;
- chat autorizado via env `TELEGRAM_CHAT_ID` (ou config) — só ele pode usar;
- recebe pedido → executa pipeline → devolve relatório resumido (11 campos);
- botões reais exigiram webhook/InlineKeyboard; aqui usamos comandos de texto
  (`/aprovar <id>`, `/recusar <id>`, `/status`, `/emergencia`).

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
from ..orchestrator.executor import executar_pedido

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
        elif comando == "status":
            pend = approvals.pendentes()
            if pend:
                _enviar(chat_id, "Pendentes:\n" + "\n".join(
                    f"`{p['id']}` {p['acao']}" for p in pend))
            else:
                _enviar(chat_id, "Nenhuma aprovação pendente.")
        elif comando == "emergencia":
            cfg = carregar_config()
            cfg.emergencia = True
            salvar_config(cfg)
            _enviar(chat_id, "🔴 Emergência acionada. Execuções pausadas.")
        elif comando == "start" or comando == "help":
            _enviar(chat_id, "Envie um pedido ou use /aprovado <id>, /recusar <id>, /status, /emergencia.")
        else:
            _enviar(chat_id, f"Comando desconhecido: /{comando}")
        return

    resposta = executar_pedido(texto)
    resposta_curta = resposta["relatorio"].get("0_resposta_curta", "")
    if resposta_curta:
        _enviar(chat_id, resposta_curta)
    else:
        _enviar(chat_id, _resumo_relatorio(resposta["relatorio"]))
    if resposta.get("handoff"):
        _enviar(chat_id, f"Transferência: {resposta['handoff']}")


def rodar_polling(intervalo_s: float = 2.0) -> None:
    """Loop de polling simples. Economia: intervalo configurável, sem IA aqui."""
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN não definido; Telegram desabilitado.")
        return
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


if __name__ == "__main__":
    rodar_polling()