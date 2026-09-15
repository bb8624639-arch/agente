"""Autosave das melhorias aprendidas no GitHub.

Quando o bot (rodando no Termux) aprende, aprova conhecimento ou cria módulo,
este módulo faz `git commit` + `push` automáticos do estado:
- exporta os conhecimentos *aprovados* para `docs/agente-memoria.md`;
- versiona quaisquer novos arquivos/módulos que estejam fora do `.gitignore`.

Controle/seguranca:
- Ligar/desligar via env `AE_GIT_AUTOSAVE` (default = "1"; "0" desliga).
- Operacao idempotente e tolerante a falhas: em erro, registra no diario e
  NUNCA derruba o bot.
- ATENCAO: o exportado vai para o remote -- se o conhecimento contiver dados
  sensiveis, mantenha o repositorio privado ou desative o autosave.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..config import PROJETO
from . import journal

# 1 = ligado (padrao); 0 = desligado
AUTOSAVE_LIGADO = os.environ.get("AE_GIT_AUTOSAVE", "1") != "0"


def _git(*args: str, cwd: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd or PROJETO, capture_output=True,
        text=True, timeout=timeout)


def exportar_memoria() -> str | None:
    """Escreve docs/agente-memoria.md com os conhecimentos aprovados."""
    from . import knowledge
    aprovados = knowledge.listar("aprovado")
    if not aprovados:
        return None
    destino = PROJETO / "docs" / "agente-memoria.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    linhas = [
        "# Memória do Agente (autosave)",
        "",
        "Conhecimentos aprovados, exportados automaticamente pelo agente "
        "para versionamento e recuperacao.",
        "",
        f"_Gerado: autosave. Total: {len(aprovados)} conhecimentos aprovados._",
        "",
    ]
    for k in reversed(aprovados):
        linhas.append(f"## {k['id']} — {k['topico']}")
        if k.get("fonte"):
            linhas.append(f"*Fonte:* {k['fonte']}")
        linhas.append("")
        linhas.append((k.get("conteudo") or "")[:4000])
        linhas.append("")
        linhas.append("---")
        linhas.append("")
    destino.write_text("\n".join(linhas), encoding="utf-8")
    return str(destino)


def sincronizar_git(mensagem: str) -> dict:
    """Commit + push automatico das mudancas (memoria + modulos/plugins).

    Retorna {"ok": bool, "detalhe": str}. Tolerante a falhas: nunca levanta.
    Nunca age com modo de teste (protecao contra push acidental em CI/tests).
    """
    if not AUTOSAVE_LIGADO:
        return {"ok": False, "detalhe": "autosave desligado (AE_GIT_AUTOSAVE=0)"}
    try:
        from ..config import carregar_config
        if getattr(carregar_config(), "modo", "teste") == "teste":
            return {"ok": False, "detalhe": "modo teste: autosave bloqueado"}
    except Exception:
        return {"ok": False, "detalhe": "sem config: autosave bloqueado"}
    exportado = exportar_memoria()

    # 1. configura identidade do git local se ainda nao tiver
    if not _git("config", "user.email").stdout.strip():
        _git("config", "user.email", "agente@autosave.local")
        _git("config", "user.name", "Agente Autosave")

    # 2. adiciona tudo que e rastreavel (memoria, modulos fora do .gitignore)
    add = _git("add", "-A")
    if add.returncode != 0:
        journal.registrar_diario("erro", "autosave git add falhou",
                                 {"saida": (add.stderr or add.stdout)[-300:]})
        return {"ok": False, "detalhe": f"git add falhou: {add.stderr[-200:]}"}

    # 3. nada a versionar?
    diff = _git("status", "--porcelain")
    if not diff.stdout.strip():
        return {"ok": True, "detalhe": "nada a versionar"}

    # 4. commit
    commit = _git("commit", "-m", f"[autosave] {mensagem[:80]}")
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        journal.registrar_diario("erro", "autosave git commit falhou",
                                 {"saida": (commit.stderr or commit.stdout)[-300:]})
        return {"ok": False, "detalhe": f"git commit falhou: {commit.stderr[-200:]}"}

    # 5. push (oferece mensagem clara se nao houver remote configurado)
    push = _git("push", "origin", "HEAD")
    if push.returncode != 0:
        journal.registrar_diario("erro", "autosave git push falhou",
                                 {"saida": (push.stderr or push.stdout)[-300:]})
        return {"ok": False, "detalhe": f"git push falhou: {push.stderr[-250:]}"}

    journal.registrar_diario("info", "autosave OK",
                             {"mensagem": mensagem, "exportado": bool(exportado)})
    return {"ok": True, "detalhe": "autosave realizado e enviado ao GitHub"}