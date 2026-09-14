#!/usr/bin/env python3
"""Entrypoint CLI do Agente Orquestrador.

Uso:
  python3 main.py                                  # interativo
  python3 main.py "pedido em linguagem natural"    # uma execução
  python3 main.py --modo teste|autonomo_controlado|producao_protegida|emergencia
  python3 main.py --emergencia                     # botão de emergência
  python3 main.py --handoff <caminho>              # reler último handoff

Modo padrão: teste (nenhuma ação externa real). Para mudar: env AE_MODO
ou a flag --modo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from autoexpand.config import MODO_PADRAO, carregar_config, salvar_config
from autoexpand.orchestrator.executor import executar_pedido


def _imprimir_relatorio(rel: dict) -> None:
    print("\n" + "=" * 64)
    print("RELATÓRIO DO ORQUESTRADOR (formato 11 itens)")
    print("=" * 64)
    campos = [
        ("Objetivo entendido", "1_objetivo_entendido"),
        ("Plano de etapas", "2_plano_de_etapas"),
        ("Agentes envolvidos", "3_agentes_envolvidos"),
        ("Ferramentas necessárias", "4_ferramentas_necessarias"),
        ("Permissões necessárias", "5_permissoes_necessarias"),
        ("Custo e consumo estimados", "6_custo_consumo_estimados"),
        ("Riscos", "7_riscos"),
        ("Ações que precisam de aprovação", "8_acoes_que_precisam_aprovacao"),
        ("Resultado dos testes", "9_resultado_dos_testes"),
        ("Próxima ação recomendada", "10_proxima_acao_recomendada"),
        ("Relatório de execução", "11_relatorio_de_execucao"),
    ]
    for nome, chave in campos:
        valor = rel.get(chave)
        print(f"\n[{nome}]")
        print(f"  {valor}")


def _modo_emergencia() -> None:
    cfg = carregar_config()
    cfg.emergencia = True
    salvar_config(cfg)
    print("BOTÃO DE EMERGÊNCIA ACIONADO: todas as execuções pausadas. Logs preservados.")
    print("Para retomar: edite state/config.json e defina emergencia=false (com aprovação).")


def _interativo() -> None:
    print(f"Agente Orquestrador — modo atual: {MODO_PADRAO}")
    print("Digite um pedido (ou 'sair', 'emergencia').\n")
    while True:
        try:
            pedido = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté mais.")
            break
        if not pedido:
            continue
        if pedido.lower() in ("sair", "exit", "quit"):
            break
        if pedido.lower() == "emergencia":
            _modo_emergencia()
            continue
        resposta = executar_pedido(pedido)
        _imprimir_relatorio(resposta["relatorio"])
        if resposta.get("handoff"):
            print(f"\nHandoff salvo em: {resposta['handoff']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente Orquestrador")
    parser.add_argument("pedido", nargs="?", help="pedido em linguagem natural")
    parser.add_argument("--modo", choices=["teste", "autonomo_controlado",
                                           "producao_protegida", "emergencia"])
    parser.add_argument("--emergencia", action="store_true", help="acionar botão de emergência")
    parser.add_argument("--handoff", metavar="ARQUIVO", help="ler um handoff existente")
    args = parser.parse_args()

    if args.emergencia:
        _modo_emergencia()
        return
    if args.handoff:
        caminho = Path(args.handoff)
        if caminho.exists():
            print(caminho.read_text(encoding="utf-8"))
        else:
            print("Handoff não encontrado:", caminho)
        return

    if args.modo:
        cfg = carregar_config()
        cfg.modo = args.modo
        salvar_config(cfg)

    if args.pedido:
        resposta = executar_pedido(args.pedido)
        _imprimir_relatorio(resposta["relatorio"])
        if resposta.get("handoff"):
            print(f"\nHandoff salvo em: {resposta['handoff']}")
        return

    _interativo()


if __name__ == "__main__":
    main()