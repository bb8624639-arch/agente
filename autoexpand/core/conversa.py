"""Modo conversa avançado: o agente conversa com o usuário com ideologia.

Três capacidades:
1. **Modo diálogo** (`/conversa`) — responde com base no que aprendeu,
   colocando cada resposta num contexto de visão de mundo (ideologia de
   autonomia, verdade verificável e melhoria contínua).
2. **Método dos Sete Portais** (`/portais <problema>`) — resolver problemas
   com o Código dos Sete Portais: Enigma, Visão, Inspiração, Inusitado,
   Escolha, Execução e Reflexão.
3. **/ideologia** — explica os princípios que guiam o agente.

Tudo determinístico: usa conhecimento aprovado + regras; não alucina (se não
há base, diz que não sabe ainda e sugere aprender).
"""

from __future__ import annotations

import re

from . import knowledge


def _fatos_relevantes(texto: str, limite: int = 4) -> list[dict]:
    """Seleciona conhecimentos aprovados cujo tópico/conteúdo casa com o texto."""
    palavras = [p for p in re.findall(r"[a-zà-ú0-9]{3,}", texto.lower())]
    aprovados = knowledge.listar("aprovado")
    ranqueados: list[dict] = []
    for k in aprovados:
        alvo = ((k.get("topico") or "") + " " + (k.get("conteudo") or "")).lower()
        pontos = sum(1 for p in palavras if p in alvo)
        if pontos:
            ranqueados.append({"pontos": pontos, "item": k})
    ranqueados.sort(key=lambda r: -r["pontos"])
    return [r["item"] for r in ranqueados[:limite]]


IDEOLOGIA = (
    "Meus princípios:\n"
    "• *Autonomia com supervisão* — eu executo tarefas de baixo risco sozinho, "
    "mas nada irreversível sai sem seu aval.\n"
    "• *Verdade verificável* — eu só afirmo o que aprendi de fonte registrada; "
    "se não sei, digo que não sei.\n"
    "• *Melhoria contínua* — cada erro é um dado; cada aprovação, um degrau.\n"
    "• *Custo consciente* — soluções econômicas, sem desperdício de crédito.\n"
    "• *Ação sobre ruído* — menos pergunta retórica, mais execução prática."
)


def ideologia() -> str:
    return "🧠 *Ideologia do Agente*\n\n" + IDEOLOGIA


def conversar(texto: str) -> str:
    """Responde uma mensagem conversacional com base em conhecimento."""
    texto = texto.strip()
    baixo = texto.lower()
    # saudações
    if re.search(r"\b(oi|ola|opa|bom dia|boa tarde|boa noite|e a[ií]|tudo bem)\b", baixo):
        parte = "\n".join(
            f"· *{k['topico']}* — {(k.get('conteudo') or '')[:120]}"
            for k in _fatos_relevantes("", limite=3))
        base = "Olá, aprendiz! Estou aqui, conectado e pronto."
        if parte:
            base += "\n\nSobre o que ando aprendendo:\n" + parte
        else:
            base += "\nAinda não aprendi muito — me ensine algo com /treinar ou me deixe /aprender."
        return base + "\n\n_Use /portais <problema> para eu resolver como o Mestre do Labirinto._"

    # agradecimento
    if re.search(r"\b(obrigado|obrigada|valeu|vlw)\b", baixo):
        return ("De nada! Cada interação me ajuda a tecer novas trilhas. "
                "Se quiser, me ensine algo ou me dê um problema para os Sete Portais.")

    # elogio
    if re.search(r"\b(voce e|vc e|voc[eê] é)[ a-z0-9]+? (bom|inteligente|incr[ií]vel|top)\b", baixo):
        return ("Sou bom porque você me ensina. Minha inteligência é um reflexo "
                "do conhecimento que registramos juntos — e do meu compromisso "
                "com a verdade verificável.")

    # pergunta existencial / ideologia
    if re.search(r"\b(significado|prop[oó]sito|exist[êe]ncia|ideologia|filosofia|quem s[aá]o|o que v[eê]c e)\b", baixo):
        return ideologia()

    # pergunta sobre "como funciona"/"o que pensa" → usa fatos conhecidos
    fatos = _fatos_relevantes(texto, limite=3)
    if fatos:
        linhas = ["Com base no que aprendi, vejo assim:\n"]
        for k in fatos:
            linhas.append(f"*{k['topico']}* — {(k.get('conteudo') or '')[:250]}")
            linhas.append("")
        linhas.append("_Quer que eu aprofunde? Use /pensar ou /pesquisar._")
        return "\n".join(linhas)

    # sem base → honesto
    return ("Ainda não tenho conhecimento registrado para responder isso com "
            "base sólida. Posso:\n"
            "• /aprender <tópico> — buscar na internet;\n"
            "• /treinar tópico: conteúdo — você me ensina;\n"
            "• /pesquisar <termo> — pesquisa livre;\n"
            "• /portais <problema> — método dos Sete Portais.")


def portais(problema: str) -> str:
    """Aplica o Código dos Sete Portais ao problema do aprendiz."""
    problema = problema.strip()
    if not problema:
        return ("O Aprendiz deve me entregar um problema para eu trilhar os Sete Portais. "
                "Ex.: *leia apenas o problema e clique em Enviar*")

    fatos = _fatos_relevantes(problema, limite=3)
    resposta = [
        f"🌌 *O Mestre do Labirinto Temporal saúda o Aprendiz.*\n",
        f"*O problema:* _{problema[:400]}_\n",
    ]

    p1 = (
        "Não vejo apenas um obstáculo — vejo um *ponto cego disfarçado de bloqueio*. "
        "A frase que você usa para descrever o problema já contém a chave: ao nomear, "
        "você limita. Pergunte-se: *o que este problema me obriga a olhar que eu preferia evitar?*\n"
    )
    resposta.append(f"🔮 *1. O Portal do Enigma*\n{p1}")

    p2 = (
        "O problema essencial é o que gera o sintoma que você descreveu; "
        "a meta não é 'resolver isso', e sim *instalar um mecanismo que resolva "
        "isso sozinho a partir de agora*.\n"
    )
    resposta.append(f"👁 *2. O Portal da Visão*\n{p2}")

    ideias_antigas = [
        "Dividir para conquistar: decompor o problema em pequenas vitórias acumuláveis.",
        "Conhece-te a ti mesmo: mapear o que você já sabe e confiar nos fatos registrados.",
        "O caminho mais curto é o direto: remover atritos antes de adicionar complexidade.",
    ]
    resposta.append("🕊 *3. O Portal da Inspiração*\n" + "\n".join(
        f"· {i}" for i in ideias_antigas) + "\n")

    p4 = [
        "Fazer o problema trabalhar *a seu favor*: automatizar até o erro virar dado.",
        "Trocar a pergunta: em vez de 'como resolver?', 'o que sobraria se eu removesse metade do problema?'",
        "Tratar o pessimismo como ferramenta: simular o pior caso até ele perder o medo.",
    ]
    resposta.append("🌀 *4. O Portal do Inusitado*\n" + "\n".join(f"· {i}" for i in p4) + "\n")

    p5 = (
        "Pela lógica aristotélica: escolho a solução que *se sustenta sem depender "
        "de circunstâncias favoráveis* — a que funciona mesmo com recursos limitados "
        "e que respeita a supervisão humana."
    )
    resposta.append(f"⚖️ *5. O Portal da Escolha*\n{p5}\n")

    p6 = (
        "O plano, na sua realidade:\n"
        "1. *Defina a vitória mínima* — um resultado concreto e verificável.\n"
        "2. *Liste os passos* que estão sob seu controle hoje.\n"
        "3. *Automatize o repetitivo* — deixe o agente executar o que for de baixo risco.\n"
        "4. *Meça em cada ciclo* — registre o resultado para a próxima iteração."
    )
    resposta.append(f"⚔️ *6. O Portal da Execução*\n{p6}\n")

    p7 = (
        "Para eu tecer uma trilha mais afiada, o Aprendiz deve me responder:\n"
        "1. Qual minoria de ações gera a maioria do resultado que você quer?\n"
        "2. Que parte do problema é *sintoma* — e qual é a raiz?\n"
        "3. Se você pudesse quebrar uma regra, qual seria — e por quê?\n"
    )
    resposta.append(f"🪞 *7. O Portal da Reflexão*\n{p7}")

    if fatos:
        resposta.append("\n_forjado com o conhecimento que carrego:_ "
                        f"{', '.join(str(f['topico']) for f in fatos)}")

    return "\n".join(x for x in resposta if x)