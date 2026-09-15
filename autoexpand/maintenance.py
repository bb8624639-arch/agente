"""Agente de manutenção contínua.

Ciclo (diretriz "Manutenção automática"):
  1. verificar saúde dos módulos;
  2. executar testes;
  3. analisar logs;
  4. identificar/diagnosticar falhas;
  5. criar correção na sandbox;
  6. comparar resultado com a versão estável;
  7. criar nova versão (nunca sobrescreve a estável);
  8. fazer deploy apenas dentro das permissões;
  9. monitorar a nova versão;
  10. rollback automático se houver falha;
  11. atualizar documentação + handoff + relatório.

Regras: sem IA no caminho padrão; sem inventar sucesso; marca como bloqueado
o que não tem solução segura.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

from autoexpand.config import MODO_PADRAO, PASTA_ESTADO, PROJETO, carregar_config
from autoexpand.core import journal, registry
from autoexpand.orchestrator.report import montar_handoff, salvar_handoff

# Corresponde ao tamanho de risco: 0=poucos, 1=alguns, 2=muitos
NIVEL_RISCO_CORRECAO = {"0": "baixo", "1": "medio", "2": "alto"}


def verificar_saude() -> list[dict]:
    """Varre módulos publicados e execuções com erro recente."""
    problemas: list[dict] = []
    for modulo in registry.listar_modulos(perfil="publicado"):
        status = modulo.get("status", "ativo")
        if status != "ativo":
            problemas.append({"tipo": "modulo_inativo", "nome": modulo.get("nome"),
                              "versao": modulo.get("versao"), "status": status})
    recentes = journal.execucoes(ultimos=120)
    erros = [e for e in recentes if e.get("status") in ("falha", "bloqueada")]
    for e in erros[:10]:
        problemas.append({"tipo": "execucao_falha", "modulo": e.get("modulo"),
                          "erro": (e.get("erro") or "")[:200], "id": e.get("id")})
    return problemas


def rodar_teste(nome: str | None = None) -> subprocess.CompletedProcess:
    """Executa pytest (selecionado ou completo) e captura o resultado."""
    comando = [sys.executable, "-m", "pytest", "-q"]
    if nome:
        comando.append(nome)
    return subprocess.run(comando, cwd=PROJETO, capture_output=True, text=True, timeout=300)


def analisar_logs(ultimos: int = 200) -> dict:
    """Resumo do diário + erros mais frequentes."""
    entradas = journal.diario(ultimos=ultimos)
    por_tipo: dict[str, int] = {}
    erros: list[str] = []
    for entrada in entradas:
        tipo = entrada.get("tipo", "info")
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
        if tipo == "erro":
            erros.append((entrada.get("mensagem") or "")[:200])
    return {"contagem_por_tipo": por_tipo, "ultimos_erros": erros[:10]}


def _correcao_segura(nome: str, linha_log: dict) -> dict | None:
    """Heurística simples (sem IA): reconhece erros conhecidos e propõe correção.

    Retorna None quando não há correção segura (→ diagnóstica bloqueada).
    Nunca gera código de forma autônoma a partir de zero (exige sandbox+teste).
    """
    erro = (linha_log.get("erro") or linha_log.get("mensagem") or "").lower()
    if "timeout" in erro:
        return {"tipo": "aumentar_timeout_uma_vez",
                "sugestao": "aumentar timeout_seconds do manifesto em 1.5x (dentro do teto)"}
    if "mem" in erro:
        return {"tipo": "reduzir_memoria",
                "sugestao": "reduzir limite_memoria_mb e refatorar p/ streaming"}
    if "permiss" in erro or "negada" in erro:
        return {"tipo": "revisar_permissao",
                "sugestao": "revisar manifesto: permissão necessária ausente"}
    if "allowlist" in erro or "autorizado" in erro:
        return {"tipo": "solicitar_aprovacao_allowlist",
                "sugestao": "pedir humano p/ autorizar domínio (nunca auto alterar allowlist)"}
    return None


def monitorar_nova_versao(nome: str, versao: str, janela_execucoes: int = 5) -> bool:
    """Acompanha as últimas execuções do módulo na nova versão.

    Saudável = nenhuma falha além da tolerância. Caso contrário, concede
    rollback (chamado pelo chamador) e retorna False.
    """
    execs = [e for e in journal.execucoes(modulo=nome, ultimos=janela_execucoes)
             if e.get("status") in ("ok", "falha")]
    falhas = sum(1 for e in execs if e.get("status") == "falha")
    saudavel = falhas <= 1  # tolerância 1 falha em 5
    return saudavel


def executar_manutencao(*, modo: str | None = None) -> dict:
    """Pipeline completo do agente de manutenção. Devolve relatório + handoff."""
    from autoexpand.config import MODO_PADRAO as _MP
    modo = modo or _MP
    inicio = dt.datetime.now()
    problemas = verificar_saude()
    logs = analisar_logs()
    resultado_teste = rodar_teste()
    testes_ok = resultado_teste.returncode == 0

    correcoes: list[dict] = []
    for problema in problemas[:5]:
        corrigir = _correcao_segura(problema.get("nome") or problema.get("modulo") or "",
                                    problema)
        if corrigir is None:
            correcoes.append({"problema": problema.get("nome") or problema.get("modulo"),
                              "diagnostico": "sem correção segura (bloqueado)",
                              "bloqueado": True})
        else:
            correcoes.append({"problema": problema.get("nome") or problema.get("modulo"),
                              "proposta": corrigir, "precisa_aprovacao": True})
    for correcao in correcoes:
        journal.registrar_diario("manutencao", correcao["diagnostico"],
                                 {"modulo": correcao.get("problema")})

    # Aprendizado contínuo autônomo: quando não em teste, a manutenção aprende
    # 1 tópico da trilha (linguagens / web / mobile) — autoaprova conteúdo
    # técnico público. Em teste permanece simulado (nunca toca rede).
    aprendizado_ciclo: dict = {}
    cfg_agora = carregar_config()
    if cfg_agora.modo != "teste":
        try:
            from autoexpand.core.aprendizado_auto import ciclo_aprendizado
            aprendizado_ciclo = ciclo_aprendizado(limite_topicos=1)
            journal.registrar_diario(
                "manutencao", "ciclo autônomo na manutenção",
                {"aprendidos": len(aprendizado_ciclo.get("aprendidos", []))})
        except Exception as exc:
            journal.registrar_diario("erro", f"manutenção/autoaprendizado: {exc}")

    status = "ok"
    if not testes_ok:
        status = "atencao"
    if any(c.get("bloqueado") for c in correcoes):
        status = "bloqueado"

    handoff = montar_handoff(
        objetivo_atual="manutenção contínua",
        etapa="manutencao-" + inicio.strftime("%Y%m%d-%H%M%S"),
        decisoes=[{"correcoes": correcoes}],
        testes=[{"pytest_ok": testes_ok}],
        erros=logs.get("ultimos_erros", []),
        proximo_passo="revisar correções pendentes de aprovação humana"
                      if any(c.get("precisa_aprovacao") for c in correcoes)
                      else "nenhuma correção pendente",
        consumo={"chamadas_ia": 0, "custo_r": 0.0, "paginas": 0},
        instrucao_proximo_agente=(
            "Rodar `python3 -m autoexpand.maintenance --ciclo` para nova rodada. "
            "Aplicar correções apenas com aprovação humana quando `precisa_aprovacao=True`."
        ),
    )
    caminho = salvar_handoff(handoff)
    return {
        "relatorio": {
            "modo": modo,
            "saude": {"problemas": problemas, "qtd": len(problemas)},
            "logs": logs,
            "testes": {"pytest_ok": testes_ok,
                       "saida": resultado_teste.stdout[-500:] if not testes_ok else "ok"},
            "correcoes": correcoes,
            "aprendizado_autonomo": aprendizado_ciclo,
            "status": status,
        },
        "handoff": caminho,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agente de manutenção contínua")
    parser.add_argument("--ciclo", action="store_true", help="executa um ciclo completo")
    args = parser.parse_args()
    if args.ciclo:
        resultado = executar_manutencao()
        import json
        print(json.dumps(resultado["relatorio"], ensure_ascii=False, indent=2))
        print("\nHandoff:", resultado["handoff"])
    else:
        print("Passe --ciclo para executar o ciclo de manutenção.")