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

from ..config import MAX_PAGINAS_POR_EXECUCAO
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


def _indice_global() -> int:
    """Posição atual na trilha infinita (persistida no config)."""
    from ..config import carregar_config
    return int(carregar_config().aprendizado_idx or 0)


def proximo_topico(trilha: str | None = None, *, idx: int | None = None) -> str:
    """Escolhe o próximo tópico da trilha (determinístico, rotaciona infinito).

    Sem `trilha`, alterna na ordem fixa linguagens → web → mobile → ...
    baseado no contador persistente `aprendizado_idx`.

    `idx` permite pedir o tópico de uma posição exata (usado pelo ciclo para
    avançar corretamente dentro de uma mesma chamada, sem depender do disco).
    """
    if idx is None:
        idx = _indice_global()
    if trilha and trilha in TRILHAS:
        sementes = TRILHAS[trilha]
        slot = idx % len(sementes)
        iteracao = (idx // len(sementes)) + 1
    else:
        trilha_atual = ORDEM_TRILHAS[idx % len(ORDEM_TRILHAS)]
        sementes = TRILHAS[trilha_atual]
        # dentro da trilha roda pelas sementes; iteração avança a cada volta
        turnover = idx // len(ORDEM_TRILHAS)
        slot = turnover % len(sementes)
        iteracao = (turnover // len(sementes)) + 1
        topico = sementes[slot]
        return f"avançado: {topico} (módulo {iteracao})" if iteracao > 1 else topico

    topico = sementes[slot]
    return f"avançado: {topico} (módulo {iteracao})" if iteracao > 1 else topico


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

    Retorna dict com id/status/auto. Usa apenas o *snippet público* da busca
    (Wikipedia ou DuckDuckGo) — nunca abre páginas completas nem toca na
    allowlist para aprendizagem (ler snippet é leitura epistêmica segura).
    """
    resultado = knowledge.aprender_autonomo(topico)
    return resultado


def ciclo_aprendizado(limite_topicos: int = 2, *, avancar: bool = True) -> dict:
    """Executa um ciclo de auto-aprendizado: escolhe N tópicos e aprende.

    Respeita o orçamento (MAX_PAGINAS_POR_EXECUCAO) e o modo. Devolve
    resumo legível para o Telegram/CLI.

    Se `avancar` (padrão), incrementa o contador persistente `aprendizado_idx`
    para o próximo ciclo seguir para a próxima posição da trilha infinita.
    """
    from ..config import carregar_config, salvar_config

    cfg = carregar_config()
    if cfg.modo == "teste":
        journal.registrar_diario(
            "info", "ciclo de aprendizado autônomo simulado (modo teste)",
            {"limite": limite_topicos})
        return {"ok": True, "simulado": True, "aprendidos": [],
                "resumo": "modo teste: nenhuma busca real; ciclo simulado.",
                "proximo_topico": proximo_topico()}

    indice = getattr(cfg, "aprendizado_idx", 0) or 0

    def _avanca() -> int:
        """Incrementa o índice local e devolve o novo valor (persistido só no fim)."""
        nonlocal indice
        indice += 1
        return indice

    limitado = min(limite_topicos, MAX_PAGINAS_POR_EXECUCAO)
    aprendidos: list[dict] = []

    def _proximo() -> str:
        """Próximo tópico na posição local — lê o índice em memória, não do disco."""
        return proximo_topico(idx=indice)

    for _ in range(limitado):
        topico = _proximo()
        if _ja_sabemos(topico):
            # evita duplicar: avança até achar um tópico ainda não aprendido
            for _ in range(len(TRILHAS) * max(len(t) for t in TRILHAS.values()) + 1):
                _avanca()
                topico = _proximo()
                if not _ja_sabemos(topico):
                    break
        try:
            r = aprender_topico(topico)
        except Exception as exc:
            journal.registrar_diario("erro", f"aprendizado autônomo falhou: {exc}")
            # mesmo sem sucesso, avança para não repetir o mesmo tópico
            if avancar:
                _avanca()
            continue
        aprendidos.append(r)
        if not r.get("auto"):
            # não-técnico: para de aprender sozinho, deixa p/ humano
            if avancar:
                _avanca()
            break
        if avancar:
            _avanca()

    if avancar:
        cfg.aprendizado_idx = indice
        salvar_config(cfg)

    journal.registrar_diario(
        "manutencao", "ciclo de aprendizado autônomo",
        {"topico": [a.get("topico") for a in aprendidos],
         "aprendidos": len(aprendidos), "indice": getattr(cfg, "aprendizado_idx", 0)})

    linhas = []
    for r in aprendidos:
        status = "✅ autoaprovado" if r.get("auto") else "📩 rascunho p/ aprovação"
        linhas.append(f"· {r.get('topico', '?')} → {status} (#{r.get('id', '?')})")
    resumo = ("🧠 *Ciclo de aprendizado autônomo*\n" +
              "\n".join(linhas) if linhas else "Nada novo no ciclo.")
    resumo += f"\n_Próximo tópico: {proximo_topico()}_"
    return {"ok": True, "simulado": False, "aprendidos": aprendidos,
            "resumo": resumo, "proximo_topico": proximo_topico()}