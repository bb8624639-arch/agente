"""Ciclo de desenvolvimento e aprendizado contínuo — autoexpansão supervisionada.

O agente se autoanalisa (diário + execuções + conhecimento + módulos) e propõe
o próximo passo de evolução sem precisar de você. A cada ciclo:
  1. Diagnostica lacunas: o que ainda não sabe, que erros repetiu, o que há
     pendente de aprovação, quais módulos já existem.
  2. Aprende com o próprio histórico: execuções bem-sucedidas viram
     conhecimento (origem "agente") e erros repetidos viram lição.
  3. Propõe evolução: uma sugestão **priorizada** de conhecimentos a buscar e
     módulos/funcionalidades a criar — sempre como rascunho, aguardando você.
  4. Reporta. Autosave acontece no chamador (bot), não aqui.

Nada disso auto-publica: segue o princípio de "autonomia com supervisão" —
o agente só *propõe*; a aprovação é sua.
"""

from __future__ import annotations

import json
import re

from . import journal, knowledge
from .persistence import consultar

CICLO_TIPOS = ("análise", "aprendizado", "proposta", "evolucao")

# Limites para não se descontrolar (autonomia supervisionada)
MAX_APRENDER_POR_CICLO = 3
MAX_PROPOSTAS_POR_CICLO = 5
MAX_ERROS_CONSIDERADOS = 8
MIN_ERROS_PALAVRA = 2  # a partir de quantas ocorrências um erro vira "recorrente"


def _palavras(texto: str) -> list[str]:
    """Palavras significativas (>= 4 letras) para casar tópicos/erros."""
    return [p for p in re.findall(r"[a-zà-ú0-9]+", texto.lower()) if len(p) >= 4]


def _erros_recentes(ultimos: int = MAX_ERROS_CONSIDERADOS) -> list[dict]:
    """Últimos erros do diário + execuções com falha."""
    diario_erros = journal.diario(tipo="erro", ultimos=ultimos)
    exec_falhas = [e for e in journal.execucoes(ultimos=80) if e.get("status") == "falha"]
    erros: list[dict] = []
    for d in diario_erros:
        erros.append({"tipo": "diario", "texto": str(d.get("mensagem", ""))[:200]})
    for e in exec_falhas:
        erros.append({"tipo": "execucao", "texto": str(e.get("erro") or "")[:200]})
    return erros


def _erros_recorrentes(erros: list[dict]) -> list[str]:
    """Agrupa por palavra-chave; devolve as que se repetem."""
    contagem: dict[str, int] = {}
    for e in erros:
        if not e["texto"]:
            continue
        for p in _palavras(e["texto"]):
            if p in ("erro", "falha", "não", "nao", "timestamp", "exception", "error"):
                continue
            contagem[p] = contagem.get(p, 0) + 1
    return [p for p, n in sorted(contagem.items(), key=lambda x: -x[1])
            if n >= MIN_ERROS_PALAVRA][:6]


def _lacunas_conhecimento() -> list[str]:
    """Tópicos que aparecem nas execuções mas não temos conhecimento aprovado."""
    aprovados = {k["topico"].lower() for k in knowledge.listar("aprovado")}
    rascunhos = {k["topico"].lower() for k in knowledge.listar("rascunho")}
    candidatos: dict[str, int] = {}
    for e in journal.execucoes(ultimos=80):
        entrada = e.get("entrada") or {}
        if isinstance(entrada, str):
            try:
                entrada = json.loads(entrada) or {}
            except Exception:
                entrada = {}
        objetivo = str(entrada.get("objetivo") or entrada.get("pedido") or "")[:120]
        palavras = _palavras(objetivo)
        for p in palavras[:4]:
            if p in aprovados or p in rascunhos:
                continue
            if p in ("crie", "criar", "script", "modulo", "quero", "poderia", "fazer", "uma", "para"):
                continue
            candidatos[p] = candidatos.get(p, 0) + 1
    return [p for p, _ in sorted(candidatos.items(), key=lambda x: -x[1])][:MAX_APRENDER_POR_CICLO]


def _propor_evolucao() -> list[dict]:
    """Propostas simples de melhoria a partir dos padrões detectados."""
    propostas: list[dict] = []
    erros = _erros_recorrentes(_erros_recentes())
    for palavra in erros:
        propostas.append({
            "tipo": "modulo",
            "titulo": f"Módulo para tratar '{palavra}'",
            "detalhe": (f"Identifiquei ocorrências repetidas de '{palavra}' nos "
                        "erros recentes. Posso criar um módulo que automatize "
                        "essa tarefa e a valide em sandbox."),
        })
    # aproveita execuções bem-sucedidas para sugerir novas capacidades
    sucesso = [e for e in journal.execucoes(ultimos=80) if e.get("status") == "ok"]
    modulos_atuais = {m.get("nome", "") for m in consultar(
        "SELECT nome FROM modulos WHERE status IN ('ativo','publicado')", ())}
    for e in sucesso[-6:]:
        modulo = str(e.get("modulo") or "")
        nome = modulo.split("/")[-1]
        if modulo and nome not in modulos_atuais and len(propostas) < MAX_PROPOSTAS_POR_CICLO:
            propostas.append({
                "tipo": "aprendizado",
                "titulo": f"Registrar aprendizado de '{nome}'",
                "detalhe": ("Esta execução funcionou em produção. Posso registrar "
                            "o padrão como conhecimento (origem 'agente') para "
                            "reutilizar em ciclos futuros."),
            })
    return propostas[:MAX_PROPOSTAS_POR_CICLO]


def _aprender_com_execucoes() -> list[dict]:
    """Aprende lições dos erros recorrentes (origem 'agente', rascunho)."""
    aprendidos: list[dict] = []
    for palavra in _erros_recorrentes(_erros_recentes()):
        try:
            id_c = knowledge.registrar(
                f"lição: {palavra}",
                f"Erros recentes citam '{palavra}' repetidamente. Padrão aprendido "
                "pelo agente: revisar esse ponto antes de executar; se persistir, "
                "criar módulo dedicado para automatizar e validar em sandbox.",
                origem="agente", fonte="ciclo_aprendizado")
            aprendidos.append({"temas": palavra, "id": id_c})
        except ValueError:
            continue
    return aprendidos


def diagnosticar() -> dict:
    """Analisa o estado atual do agente e propõe o próximo ciclo de evolução.

    Devolve dict com relatório de texto para o usuário + campos estruturados.
    """
    erros = _erros_recentes()
    recorrentes = _erros_recorrentes(erros)
    lacunas = _lacunas_conhecimento()
    propostas = _propor_evolucao()
    aprendidos = _aprender_com_execucoes()

    # aprende de verdade (rascunho aguardando aprovação)
    for ap in aprendidos:
        journal.registrar_diario(
            "info", "ciclo aprendeu lição",
            {"topico": ap["temas"], "id": ap["id"],
             "aviso": "rascunho aguardando /aprovar_conh"})

    estat = _estatisticas_rapidas()

    def _bloco(titulo: str, itens: list[str]) -> str:
        if not itens:
            return f"*{titulo}:* —"
        return f"*{titulo}:*\n" + "\n".join(f"· {i}" for i in itens)

    texto = ("🔄 *Ciclo de evolução — diagnóstico*\n\n"
             f"*Conhecimento:* {estat['conhecimento']}\n"
             f"*Módulos:* {estat['modulos']}\n\n")
    texto += _bloco("Lacunas de conhecimento", lacunas) + "\n"
    texto += _bloco("Erros recorrentes", recorrentes) + "\n"
    texto += _bloco("Aprendizados gerados (rascunho)", [f"#{a['id']} {a['temas']}" for a in aprendidos]) + "\n"
    texto += _bloco("Propostas de evolução", [p["titulo"] for p in propostas]) + "\n"
    texto += ("\n_Quer que eu aja em alguma? Aprove os aprendizados com "
              "`/aprovar_conh <id>` ou peça `/criar_modulo` para eu gerar "
              "um módulo novo. Autonomia supervisionada: eu proponho, você decide._")

    return {
        "texto": texto,
        "lacunas": lacunas,
        "erros_recorrentes": recorrentes,
        "aprendidos": aprendidos,
        "propostas": propostas,
        "estatisticas": estat,
    }


def _estatisticas_rapidas() -> dict:
    """Números rápidos de conhecimento e módulos para o diagnóstico."""
    conh = consultar(
        "SELECT status, COUNT(*) n FROM conhecimento GROUP BY status", ())
    mods = consultar(
        "SELECT perfil, COUNT(*) n FROM modulos GROUP BY perfil", ())
    return {
        "conhecimento": ", ".join(f"{r['status']}:{r['n']}" for r in conh) or "vazio",
        "modulos": ", ".join(f"{r['perfil']}:{r['n']}" for r in mods) or "vazio",
    }


def proximo_passo() -> dict:
    """Decide (regra) qual o **próximo passo** mais valioso agora.

    Usado pelo comando /evoluir para dar uma recomendação objetiva.
    """
    pendentes = knowledge.listar("rascunho")
    if pendentes:
        p = pendentes[-1]
        return {"acao": "aprovar", "detalhe": f"Aprove /aprovar_conh {p['id']} "
                                              f"({p['topico'][:60]})",
                "alvo": str(p["id"])}
    mods_rascunho = consultar("SELECT nome FROM modulos WHERE perfil='rascunho'", ())
    if mods_rascunho:
        return {"acao": "criar_modulo", "detalhe": "Há módulo(s) rascunho a desenvolver",
                "alvo": mods_rascunho[0]["nome"]}
    lacunas = _lacunas_conhecimento()
    if lacunas:
        return {"acao": "aprender",
                "detalhe": f"Recupere conhecimento pendente: {lacunas[0]}",
                "alvo": lacunas[0]}
    return {"acao": "criar_modulo",
            "detalhe": "Crie um módulo novo para evoluir o agente",
            "alvo": ""}