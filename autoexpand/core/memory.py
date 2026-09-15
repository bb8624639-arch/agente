"""Memória ativa e "pensamento" determinístico do agente.

Capacidade de *pensar* sem LLM: sintetiza conhecimento aprovado, ultimas
execuções e erros para produzir resumos, conexoes e sugestoes acionáveis.
Complementa `knowledge`, que guarda saber; aqui fica o *raciocinio*,
que agrega em bloco e responde perguntas sobre o que ele sabe.

Nada disso é alucinação: é agregação determinística dos próprios registros,
com seções claras (""/fatos/deduções/dúvidas/sugestões/passos").
"""

from __future__ import annotations

import re

from . import knowledge, journal
from .persistence import consultar


def _secao(nome: str, itens: list) -> str:
    if not itens:
        return ""
    linhas = [f"*{nome}*", "· " + "\n· ".join(" ".join(str(i).split()) for i in itens)]
    return "\n".join(linhas)


def pensar(pergunta: str = "", *, limite_fatos: int = 12) -> dict:
    """Sintetiza o que o agente sabe (aprovado), ultimos erros/passos e
    devolve resumo + deduções + próximos passos.

    Retorna dict serializável com `texto_resposta` pronto para o Telegram.
    """
    # 1. fatos: conhecimento aprovado mais recente
    fatos = knowledge.listar("aprovado")
    fatos_curtos = [
        {"id": k["id"], "topico": k["topico"],
         "conteudo": " ".join((k.get("conteudo") or "").split())[:350]}
        for k in fatos[:limite_fatos]
    ]

    # 2. contexto dinâmico: últimas execuções ok/falha + diário recente
    execs = journal.execucoes(ultimos=8)
    diario = journal.diario(tipo="erro", ultimos=5)

    objetivos_recentes = [
        {"id": e["id"], "modulo": e.get("modulo", ""),
         "status": e.get("status", ""), "erro": (e.get("erro") or "")[:120]}
        for e in execs
    ]
    erros = [(d.get("mensagem") or "")[:150] for d in diario]

    # 3. pontos cegos: tópicos rascunho (ainda sem aprovação)
    rascunhos = knowledge.listar("rascunho")
    pendentes = [{"id": r["id"], "topico": r["topico"]} for r in rascunhos[:6]]

    # 4. sugestões determinísticas a partir dos padrões
    sugestoes: list[str] = []
    if pendentes:
        sugestoes.append(
            "Aprove os conhecimentos pendentes: " +
            ", ".join(f"/aprovar_conh {p['id']} ({p['topico']})" for p in pendentes[:3]))
    if erros:
        sugestoes.append(
            f"Há {len(erros)} erros recentes no diário. Rode /status para ver aprovações "
            "ou /aprender para pesquisar solução.")
    if not fatos and not pendentes and not erros:
        sugestoes.append(
            "Ainda não aprendi nada. Use *Aprender da internet* ou *Ensinar* no menu.")

    # 5. responder à pergunta se for uma busca simples sobre fatos conhecidos
    resposta_direta = ""
    if pergunta.strip():
        resposta_direta = _resposta_sobre(pergunta, fatos)

    partes = [_secao("Fatos conhecidos", [f"#{f['id']} {f['topico']}: {f['conteudo']}"
                                          for f in fatos_curtos]),
              _secao("Execuções recentes", [f"#{e['id']} {e['modulo']} → {e['status']}"
                                            + (f" ({e['erro']})" if e.get("erro") else "")
                                            for e in objetivos_recentes]),
              _secao("Erros recentes", erros) if erros else "",
              _secao("Pendências", [f"#{p['id']} {p['topico']}" for p in pendentes]),
              _secao("Sugestões", sugestoes),
              ]

    texto = "\n".join(p for p in partes if p) or "*Nada para pensar ainda.*"
    if resposta_direta:
        texto = f"{resposta_direta}\n\n————\n{texto}"

    return {
        "texto_resposta": texto,
        "fatos": fatos_curtos, "execucoes": objetivos_recentes,
        "erros": erros, "pendentes": pendentes, "sugestoes": sugestoes,
        "resposta_direta": resposta_direta,
    }


def _resposta_sobre(pergunta: str, fatos: list[dict]) -> str:
    """Se a pergunta mencionar um tópico conhecido, responde com o fato."""
    palavras = re.findall(r"[a-zà-ú0-9]+", pergunta.lower())
    for fato in fatos:
        topico = str(fato.get("topico", "")).lower()
        conteudo = str(fato.get("conteudo", "")).lower()
        # casa se alguma palavra significativa do tópico aparecer na pergunta
        if any(len(p) >= 4 and p in topico for p in palavras) or \
           any(len(p) >= 4 and p in conteudo for p in palavras):
            return (f"*Você perguntou sobre:* {fato['topico']}\n"
                    f"*Fato que eu sei:* {conteudo[:500]}")
    return ""


def estatisticas() -> dict:
    """Totais rápidos para /status: conhecimento, módulos, erros, consumo."""
    conh = consultar(
        "SELECT status, COUNT(*) n FROM conhecimento GROUP BY status", ())
    mods = consultar(
        "SELECT perfil, COUNT(*) n FROM modulos GROUP BY perfil", ())
    err_hoje = journal.execucoes(ultimos=50)
    return {
        "conhecimento": {r["status"]: r["n"] for r in conh},
        "modulos": {r["perfil"]: r["n"] for r in mods},
        "erros_recentes": sum(1 for e in err_hoje if e.get("status") == "falha"),
    }