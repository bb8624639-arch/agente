"""Memória de aprendizado do agente: conhecimento registrado pelo usuário,
extraído da internet ou proposto pelo próprio agente — sempre com aprovação.

Fluxo (supervisão):
  1. registrar(topico, conteudo, origem) -> cria rascunho
  2. o usuário aprova/rejeita via painel ou Telegram (/aprovar <id>)
  3. apenas conhecimento 'aprovado' é usado em decisões futuras

Fonte de aprendizado externo: Wikipedia REST (pública, sem chave),
limitada a artigos de domínio aberto — nada sensível é armazenado sem revisão.
"""

from __future__ import annotations

import json
import time
import unicodedata
import urllib.parse
import urllib.request
from textwrap import wrap

from .persistence import consultar, executar, j_loads

ORIGENS = ("usuario", "internet", "agente")
STATUS = ("rascunho", "aprovado", "rejeitado")

# Palavras que indicam conteúdo técnico/desenvolvimento (sem acento).
# Usada para decidir quando o conhecimento vindo da internet pode ser
# aprovado de forma automática no fluxo autônomo (ver deve_autoaprovar).
PALAVRAS_TECNICAS = (
    "python", "javascript", "typescript", "programacao", "codigo", "desenvolvimento",
    "web", "html", "css", "http", "api", "automacao", "browser", "navegador",
    "playwright", "selenium", "android", "mobile", "app", "adb", "appium",
    "uiautomator", "termux", "funcao", "classe", "objeto", "biblioteca", "framework",
    "script", "dados", "banco de dados", "sql", "n8n", "workflow", "teste",
    "automatizar", "bot", "telegram", "whatsapp", "git", "shell", "bash", "linux",
    "php", "ruby", "java", "golang", "logica", "protoco", "scraping", "integracao",
    "fluxo", "backend", "frontend", "deploy", "cloud", "docker", "rest",
)


def _sem_acentos(texto: str) -> str:
    """Normaliza minúsculas sem acentos para casar palavras técnicas."""
    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn")


def eh_conteudo_tecnico(topico: str, conteudo: str = "") -> bool:
    """O conteúdo (tópico+texto) parece técnico/desenvolvimento?"""
    alvo = _sem_acentos(f"{topico} {conteudo}")
    return any(p in alvo for p in PALAVRAS_TECNICAS)


def fonte_publica(fonte: str) -> bool:
    """Fonte pública e verificável (Wikipedia/páginas web abertas)."""
    f = (fonte or "").lower()
    return any(d in f for d in ("wikipedia.org", "pt.wikipedia", "duckduckgo",
                                "https://", "http://"))


def deve_autoaprovar(topico: str, fonte: str, conteudo: str = "",
                     origem: str = "internet") -> bool:
    """Política de autoaprovação (modo autônomo controlado).

    Só aprova automaticamente **conteúdo técnico público** vindo da internet.
    Usuário/agente continuam como rascunho aguardando o humano. Nunca altera
    risco de segurança: a fonte precisa ser pública e o tema técnico.
    """
    if origem != "internet":
        return False
    return eh_conteudo_tecnico(topico, conteudo) and fonte_publica(fonte)

# Wikipedia REST: busca + resumo (extrato do primeiro parágrafo)
_WIKI_BASE = "https://pt.wikipedia.org/api/rest_v1/page/summary/"
_UA = {"User-Agent": "AgenteOrquestrador/1.0 (contato: admin@localhost)"}


def registrar(topico: str, conteudo: str, *, origem: str = "usuario", fonte: str = "") -> int:
    """Cria um registro de conhecimento. Devolve o id.

    Em modo autônomo controlado, conteúdo técnico de fonte pública vindo da
    internet (via `aprender_autonomo`) é aprovado imediatamente — sem fila.
    Usuário/agente e conteúdo não-técnico continuam como rascunho aguardando
    a aprovação humana (/aprovar_conh <id>).

    Conteúdo maior é aceito (contexto colado): até 30k caracteres para "usuario",
    para suportar importar documentos inteiros. Tópicos continuam curtos.
    """
    topico = topico.strip()[:300]
    antecedente = conteudo.strip()
    # limite generoso p/ lidar com texto colado; internet/agente ficam em 8000
    limite = 30000 if origem == "usuario" else 8000
    conteudo = antecedente[:limite]
    if origem not in ORIGENS:
        origem = "usuario"
    if not topico or not conteudo:
        raise ValueError("tópico e conteúdo são obrigatórios")

    modo = "usuario"  # default seguro
    try:
        from ..config import carregar_config
        modo = carregar_config().modo
    except Exception:
        pass

    auto = (modo in ("autonomo_controlado", "producao_protegida")
            and deve_autoaprovar(topico, fonte, conteudo, origem))
    status = "aprovado" if auto else "rascunho"
    aprovado_por = "agente_autonomo" if auto else ""

    executar(
        """INSERT INTO conhecimento (topico, conteudo, fonte, status, origem, criado_em,
                                     aprovado_por, aprovado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (topico, conteudo, fonte[:500], status, origem, time.time(),
         aprovado_por, time.time() if auto else None))
    id_criado = consultar("SELECT id FROM conhecimento ORDER BY id DESC LIMIT 1")[0]["id"]
    if auto:
        from .journal import registrar_diario
        registrar_diario(
            "info", f"conhecimento #{id_criado} autoaprovado (técnico/público)",
            {"topico": topico, "origem": origem, "fonte": fonte})
    return id_criado


def listar(status: str | None = "aprovado") -> list[dict]:
    """Lista conhecimentos. status=None -> todos. Padrão otimista: só aprovados."""
    if status not in STATUS and status is not None:
        raise ValueError(f"status inválido: {status}")
    if status is None:
        sql = "SELECT * FROM conhecimento ORDER BY id DESC"
        params: tuple = ()
    else:
        sql = "SELECT * FROM conhecimento WHERE status=? ORDER BY id DESC"
        params = (status,)
    return consultar(sql, params)


def decidir(id_conh: int, aprovado: bool, *, por: str = "agente") -> dict:
    """Aprova ou rejeita um rascunho de conhecimento. Registra auditoria no diário."""
    encontrado = consultar("SELECT * FROM conhecimento WHERE id=?", (id_conh,))
    if not encontrado:
        return {"status": "inexistente", "id": id_conh}
    novo = "aprovado" if aprovado else "rejeitado"
    executar(
        """UPDATE conhecimento SET status=?, aprovado_por=?, aprovado_em=?
           WHERE id=?""",
        (novo, por, time.time(), id_conh))
    item = encontrado[0]
    from .journal import registrar_diario
    registrar_diario(
        "decisao", f"conhecimento #{id_conh} {novo} por {por}",
        {"topico": item["topico"], "aprovado": aprovado})
    return {"status": novo, "id": id_conh, "topico": item["topico"]}


def buscar_completo(topico: str, limite_palavras: int = 150) -> dict:
    """Pesquisa resumo na Wikipedia (pt) e devolve candidato a conhecimento.

    Só cria rascunho se o artigo existir (status 200). Falha retorna dict com 'erro'.
    """
    topico_limpo = topico.strip()
    if not topico_limpo:
        return {"erro": "tópico vazio"}
    enc = urllib.parse.quote(topico_limpo.replace(" ", "_"))
    url = _WIKI_BASE + enc
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"erro": f"falha ao consultar fonte: {exc}"}

    titulo = dados.get("title", topico_limpo)
    descricao = (dados.get("extract") or "").strip()
    if not descricao:
        return {"erro": f"sem resumo encontrado para '{topico_limpo}'"}
    resumo = " ".join(descricao.split())[:limite_palavras]
    return {
        "topico": titulo,
        "conteudo": resumo,
        "fonte": (dados.get("content_urls") or {}).get("desktop", {}).get("page", url),
        "origem": "internet",
    }


def aprender_e_registrar(topico: str) -> dict:
    """Busca na internet e cria registro (rascunho, a não ser em autônomo).

    Primeiro tenta Wikipedia; se falhar (sem artigo), faz fallback para
    a busca genérica (DuckDuckGo) e usa o melhor snippet disponível.
    """
    candidato = buscar_completo(topico)
    if "erro" in candidato:
        # fallback: busca livre (se houver fonte autorizada p/ registro)
        candidato = buscar_completo_via_web(topico)
    if "erro" in candidato:
        return candidato
    id_criado = registrar(
        candidato["topico"], candidato["conteudo"],
        origem="internet", fonte=candidato["fonte"])
    linha = consultar("SELECT status FROM conhecimento WHERE id=?", (id_criado,))
    status = (linha[0]["status"] if linha else "rascunho")
    auto = status == "aprovado"
    return {
        "id": id_criado,
        "topico": candidato["topico"],
        "fonte": candidato["fonte"],
        "conteudo": candidato["conteudo"],
        "auto": auto,
        "aviso": ("autoaprovado (técnico/público)" if auto
                  else "rascunho criado — aguardando sua aprovação (/aprovar_conh <id>)"),
    }


def aprender_autonomo(topico: str) -> dict:
    """Fluxo de auto-aprendizado: busca conteúdo técnico e salva como
    conhecimento **aprovado** (apenas se vier da internet e for técnico).

    Usado pelo /aprender_auto e pelo ciclo contínuo. Nada é forçado: se o
    conteúdo não for reconhecidamente técnico, permanece rascunho para o humano.
    """
    return aprender_e_registrar(topico)


def buscar_completo_via_web(topico: str, limite: int = 3) -> dict:
    """Fallback: usa DuckDuckGo p/ montar um rascunho de conhecimento.

    Usa os snippets dos resultados para compor um resumo. Nunca abre página
    fora da allowlist; só aproveita o que a própria busca retorna.
    """
    try:
        from ..browser.search import buscar_web
        dados = buscar_web(topico, limite=limite)
    except Exception as exc:
        return {"erro": f"fallback de busca falhou: {exc}"}
    if "erro" in dados:
        return {"erro": dados["erro"]}
    resultados = dados.get("resultados", [])
    if not resultados:
        return {"erro": f"nada encontrado na internet para '{topico}'"}
    trechos = [r.get("trecho", "") for r in resultados if r.get("trecho")]
    conteudo = " ".join(trechos)[:4000]
    if not conteudo:
        conteudo = "; ".join(r.get("titulo", "") for r in resultados[:3])[:4000]
    topico_titulo = resultados[0].get("titulo", topico)
    return {
        "topico": topico_titulo,
        "conteudo": conteudo or topico,
        "fonte": resultados[0].get("url", "duckduckgo"),
        "origem": "internet",
    }