"""Gerador de módulos/plugins — autoexpansão por scripts com supervisão.

Fluxo (controlado):
  1. Recebe pedido (ex.: "crie um script que dobre um número").
  2. Gera o arquivo-fonte em `autoexpand/plugins/` (Python/JS/TS) + manifesto.
  3. Valida o manifesto (núcleo de plugin) e testa em sandbox.
  4. Publica no registry (versão) **somente após sua aprovação**.
  5. Executa resposta curta com o resultado do teste.

Nunca auto-concede permissões; aprovação é feita via painel/Telegram.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from ..config import PROJETO, PASTA_PLUGINS
from ..core import registry
from ..core.plugin import SchemaInvalido, normalizar_manifesto

RUNTIME_DE_NOME = {
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "shell": "shell",
}

EXTENSAO = {"python": "py", "javascript": "js", "typescript": "ts", "shell": "sh"}


def _slug(nome: str) -> str:
    """Gera nome de arquivo seguro a partir do pedido."""
    return re.sub(r"[^a-z0-9_]+", "_", nome.lower()).strip("_")[:40] or "modulo"


def _corpo_python(nome: str) -> str:
    return f'''"""Módulo gerado: {nome}.

Gerado pelo Agente Orquestrador — revisado e aprovado antes de publicar.
"""


def executar(entrada: dict) -> dict:
    """Lógica principal. Devolva um dict serializável."""
    return {{"recebido": entrada, "ok": True}}
'''


def _corpo_javascript(nome: str) -> str:
    return f'''// Módulo gerado: {nome}.
// Gerado pelo Agente Orquestrador — revisado e aprovado antes de publicar.

export function executar(entrada) {{
    return {{ recebido: entrada, ok: true }};
}}
'''


def _corpo(perfil: str, nome: str, runtime: str) -> str:
    if runtime == "python":
        return _corpo_python(nome)
    return _corpo_javascript(nome)


def gerar_modulo(pedido: str | None = None, *, nome: str = "", runtime: str = "python",
                 entrada_amostra: dict | None = None,
                 codigo_extra: str = "") -> dict:
    """Gera um rascunho de módulo (arquivo + manifesto) e publica aguardando aprovação.

    Devolve:
      ok=True → { caminho, nome, versao, manifesto, ap_id, aprovacao_pendente }
      ok=False → erro legível (nome/runtime inválido etc.)
    """
    nome = (nome or "").strip()
    if not nome:
        # tenta inferir do pedido
        if pedido:
            m = re.search(r"(?:script|m[oó]dulo|plugin|ferramenta)[^a-z]*([a-z0-9_ ]+)",
                          pedido, re.I)
            if m:
                nome = m.group(1).strip()
        nome = nome or "modulo_generico"
    nome = _slug(nome)
    if runtime not in RUNTIME_DE_NOME:
        return {"ok": False, "erro": f"runtime não suportado: {runtime}"}

    # gera código-base (determinístico) + extra opcional do usuário
    base = _corpo("rascunho", nome, runtime)
    if codigo_extra.strip():
        if runtime == "python":
            # injeta no corpo no lugar do return simples (meio)
            base = base.replace(
                'return {"recebido": entrada, "ok": True}',
                codigo_extra.strip().rstrip())
        else:
            base += "\n" + codigo_extra.strip()

    PASTA_PLUGINS.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_PLUGINS / f"{nome}.{EXTENSAO[runtime]}"
    arquivo.write_text(base, encoding="utf-8")
    manifesto = normalizar_manifesto({
        "nome": nome, "versao": "1.0.0", "perfil": "rascunho",
        "runtime": runtime,
        "permissoes": ["ler_api"] if runtime == "python" else [],
        "timeout_seconds": 30, "limite_memoria_mb": 128,
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "script": {runtime: base},
        "descricao": pedido or "módulo gerado pelo agente",
        "aprovado": False,
    })

    # testa em sandbox se possível (usa executar_python direto, sem Tarefa)
    teste_ok = "não testado"
    try:
        from ..core.sandbox_runner import executar_python
        r = executar_python(base, (entrada_amostra or {"n": 2}), 30, 128)
        teste_ok = bool(r.get("ok", False)) if isinstance(r, dict) else bool(r)
    except Exception as exc:
        teste_ok = f"erro no sandbox: {exc}"

    # publica como rascunho e cria aprovação (nunca publica sem você)
    registry.registrar_manifesto(manifesto)
    ap_id = None
    try:
        from ..core.approvals import criar_aprovacao
        ap_id = criar_aprovacao("publicar_modulo", modulo=nome,
                                contexto={"modulo": nome,
                                          "versao": manifesto["versao"],
                                          "pedido": pedido})
    except Exception:
        ap_id = None

    return {
        "ok": True,
        "nome": nome, "versao": manifesto["versao"],
        "runtime": runtime, "caminho": str(arquivo),
        "manifesto": manifesto, "ap_id": ap_id,
        "teste": teste_ok,
        "aprovacao_pendente": True,
        "msg": (f"Módulo {nome} v{manifesto['versao']} gerado em {arquivo.name}. "
                f"Teste: {teste_ok}. Aprovando via /aprovado {ap_id} para publicar."),
    }


def publicar_modulo_aprovado(nome: str, por: str = "agente") -> dict:
    """Após aprovação do usuário, marca o módulo como publicado."""
    manifesto = registry.versao_atual(nome)
    if not manifesto:
        return {"ok": False, "erro": f"módulo {nome} não encontrado"}
    publicado = registry.publicar(nome, manifesto, por=por, aprovado=True,
                                  motivo="aprovado pelo usuário")
    return {"ok": True, "nome": nome, "versao": publicado.get("versao")}