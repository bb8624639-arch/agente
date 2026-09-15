"""Aprendizado autônomo contínuo — trilhas de estudo de programação/web/mobile.

O agente mantém um "currículo infinito" de tópicos técnicos distribuídos em
trilhas (linguagens, automação web, automação mobile) e, a cada ciclo,
aprende o próximo tópico **sem pedir aprovação** — desde que o conteúdo venha
da internet e seja reconhecidamente técnico (ver knowledge.deve_autoaprovar).

Controles:
- Respeita o orçamento de páginas (browser/budget) e o modo do sistema.
- Em modo `teste` não toca a rede: executa simulado e devolve status.
- Nunca aprende um tópico que já exista (aprovado/rascunho) — evita duplicar.
- A ordem das trilhas é determinística e infinita (rotaciona quando acaba).

Trilhas:
  1. linguagens  — Python, JavaScript, TypeScript, PHP, Ruby, Go, SQL...
  2. web         — HTTP, HTML, CSS, Playwright, Selenium, REST, APIs...
  3. mobile      — Android, ADB, Termux, Appium, UIAutomator, automatização...
"""

from __future__ import annotations

import time

from ..config import MODO_PADRAO, MAX_PAGINAS_POR_EXECUCAO
from ..core import knowledge, journal
from ..core.persistence import consultar

# Tópicos "semente" por trilha — cada um gera variações infinitas no ciclo.
TRILHAS: dict[str, list[str]] = {
    "linguagens": [
        "programação em Python",
        "programação em JavaScript",
        "programação em TypeScript",
        "programação em SQL",
        "programação em Go",
        "programação em Ruby",
        "programação em PHP",
        "programação em Java",
    ],
    "web": [
        "automação web com Playwright",
        "automação web com Selenium",
        "HTTP e APIs REST",
        "HTML e CSS para scraping",
        "browser automation headless",
        "integração com n8n",
    ],
    "mobile": [
        "automação no Android com ADB",
        "automação mobile com Appium",
        "UIAutomator e acessibilidade",
        "Termux para automação no celular",
        "webhooks e intents no Android",
    ],
}

ORDEM_TRILHAS = ("linguagens", "web", "mobile")

# Tamanho da trilha "infinita": após esgotar as sementes, o ciclo gera
# variações numeradas (ex.: "avançado: [tópico] #2").
MAX_SEMENTES_POR_TRILHA = len(max(TRILHAS.values(), key=len))


def trilhas_disponiveis() -> dict[str, list[str]]:
    return {nome: list(t) for nome, t in TRILHAS.items()}


def proximo_topico(trilha: str | None = None) -> str:
    """Escolhe o próximo tópico da trilha (determinístico, rotaciona infinito).

    Se `trilha` é None, alterna pelas trilhas em ordem fixa com base no
    contador de execuções do ciclo.
    """
    if trilha and trilha in TRILHAS:
        sementes = TRILHAS[trilha]
    else:
        # roda pelas trilhas em sequência (linguagens → web → mobile → ...)
        idx = _contador_execucoes() % len(ORDEM_TRILHAS)
        trilha = ORDEM_TRILHAS[idx]
        sementes = TRILHAS[trilha]

    # já aprendemos quantas sementes? Ex: n aprendidas → próximo ímpeto
    aprendidos = _quantos_aprendidos()
    indice_semente = aprendidos % len(sementes)
    iteracao = (aprendidos // len(sementes)) + 1
    topico = sementes[indice_semente]
    if iteracao > 1:
        return f"avançado: {topico} (módulo {iteracao})"
    return topico


def _contador_execucoes() -> int:
    """Conta execuções do módulo autônomo para variar a trilha."""
    r = consultar("SELECT COUNT(*) n FROM execucoes WHERE modulo='core/aprendizado_auto'", ())
    return int(r[0]["n"]) if r else 0


def _quantos_aprendidos() -> int:
    """Conhecimentos aprovados com origem 'agente' (as lições/técnicas)."""
    r = consultar(
        "SELECT COUNT(*) n FROM conhecimento WHERE origem='agente' AND status='aprovado'", ())
    return int(r[0]["n"]) if r else 0


def _ja_sabemos(topico: str) -> bool:
    """True se já temos conhecimento (aprovado ou rascunho) sobre o tópico."""
    alvo = " ".join(topico.lower().split())
    linhas = consultar(
        "SELECT topico, conteudo FROM conhecimento WHERE status IN ('aprovado','rascunho')", ())
    for linha in linhas:
        if alvo in (linha["topico"] or "").lower():
            return True
        if alvo in (linha["conteudo"] or "").lower()[:300]:
            # casa parcialmente (palavra-chave do alvo no início do conteúdo)
            pass
    # falha leve: checa palavra mais longa do tópico
    palavras = [p for p in alvo.replace(" (", " ").split() if len(p) >= 6]
    for linha in linhas:
        conteudo = (linha["conteudo"] or "").lower()
        if any(p and p in conteudo for p in palavras[:3]):
            return True
    return False


def aprender_topico(topico: str) -> dict:
    """Aprende um tópico autônomo (busca internet → registra conhecimento).

    Retorna dict com id/status/auto. Nunca abre páginas fora da allowlist;
    apenas usa o resumo da busca (Wikipedia ou DuckDuckGo).
    """
    resultado = knowledge.aprender_autonomo(topico)
    return resultado


def ciclo_aprendizado(limite_topicos: int = 2) -> dict:
    """Executa um ciclo de auto-aprendizado: escolhe N tópicos e aprende.

    Respeita o orçamento (MAX_PAGINAS_POR_EXECUCAO) e o modo. Devolve
    resumo legível para o Telegram/CLI.
    """
    from ..config import carregar_config

    cfg = carregar_config()
    if cfg.modo == "teste":
        journal.registrar_diario(
            "info", "ciclo de aprendizado autônomo simulado (modo teste)",
            {"limite": limite_topicos})
        return {"ok": True, "simulado": True, "aprendidos": [],
                "resumo": "modo teste: nenhuma busca real; ciclo simulado."}

    topico_sugerido = proximo_topico()
    if _ja_sabemos(topico_sugerido):
        # pula para próximo seguindo a ordem das sementes (sem duplicar)
        for trilha in ORDEM_TRILHAS:
            for _ in range(MAX_SEMENTES_POR_TRILHA):
                candidato = proximo_topico(trilha)
                if not _ja_sabemos(candidato):
                    topico_sugerido = candidato
                    break
            if not _ja_sabemos(topico_sugerido):
                break

    limitado = min(limite_topicos, MAX_PAGINAS_POR_EXECUCAO)
    aprendidos: list[dict] = []
    for i in range(limitado):
        topico = topico_sugerido if i == 0 else proximo_topico()
        try:
            r = aprender_topico(topico)
        except Exception as exc:
            journal.registrar_diario("erro", f"aprendizado autônomo falhou: {exc}")
            continue
        aprendidos.append(r)
        if not r.get("auto"):
            break  # não-técnico: para de aprender sozinho, deixa p/ humano

    journal.registrar_diario(
        "manutencao", "ciclo de aprendizado autônomo",
        {"topico": topico_sugerido, "aprendidos": len(aprendidos)})

    linhas = []
    for r in aprendidos:
        status = "✅ autoaprovado" if r.get("auto") else "📩 rascunho p/ aprovação"
        linhas.append(f"· {r.get('topico', '?')} → {status} (#{r.get('id', '?')})")
    resumo = ("🧠 *Ciclo de aprendizado autônomo*\n" +
              "\n".join(linhas) if linhas else "Nada novo no ciclo.")
    return {"ok": True, "simulado": False, "aprendidos": aprendidos,
            "resumo": resumo}