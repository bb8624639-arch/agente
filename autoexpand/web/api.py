"""API de integração para o painel existente (sem reconstruí-lo).

O painel é um cliente consumidor desta API. Endpoints:
  GET  /api/modulos                   lista módulos + versões
  GET  /api/modulos/<nome>/versoes     histórico de versões
  POST /api/aprovacoes/<id>/decidir    aprovar/recusar
  GET  /api/aprovacoes/pendentes       fila de aprovações
  POST /api/emergencia                 acionar/liberar botão de emergência
  GET  /api/consumo                    contadores consolidados
  GET  /api/limites                    tetos de economia
  POST /api/sites/autorizar            adicionar domínio à allowlist
  POST /api/sites/remover              remover domínio da allowlist
  GET  /api/diario                     últimas entradas do diário

Auth: opcional via env AE_API_TOKEN (Bearer). Sem token → aberto (dev).
Contrato documentado em docs/contrato-painel.md.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, request

from ..config import (MODO_PADRAO, carregar_config, limites_json, salvar_config)
from ..browser.allowed import (acesso_livre, autorizar_dominio,
                               definir_acesso_livre, dominios_autorizados,
                               remover_dominio)
from ..core import approvals, journal, budget, registry

API_TOKEN = os.environ.get("AE_API_TOKEN", "")
API_MODO_EXECUCAO = os.environ.get("AE_API_EXECUCAO", "permitida")

app = Flask(__name__)


def _autorizado() -> bool:
    if not API_TOKEN:
        return True
    header = request.headers.get("Authorization", "")
    return header == f"Bearer {API_TOKEN}"


@app.before_request
def _guard():
    if request.path.startswith("/api/") and not _autorizado():
        return jsonify({"erro": "não autorizado"}), 401


@app.get("/api/modulos")
def modulos():
    return jsonify({"modos": MODO_PADRAO, "modulos": registry.listar_modulos(),
                    "dominios_autorizados": dominios_autorizados()})


@app.get("/api/modulos/<nome>/versoes")
def versoes(nome: str):
    return jsonify({"versoes": registry.historico_versoes(nome)})


@app.post("/api/aprovacoes/<ap_id>/decidir")
def decidir_aprovacao(ap_id: str):
    corpo = request.get_json(silent=True) or {}
    aprovado = bool(corpo.get("aprovado"))
    por = str(corpo.get("por", "humano"))[:120]
    linha = approvals.decidir(ap_id, aprovado, por=por)
    if not linha:
        return jsonify({"erro": "aprovação não encontrada"}), 404
    journal.registrar_diario("decisao",
                             f"{'aprovado' if aprovado else 'recusado'} {ap_id} por {por}")
    return jsonify(linha)


@app.get("/api/aprovacoes/pendentes")
def aprovacoes_pendentes():
    return jsonify({"pendentes": approvals.pendentes()})


@app.post("/api/emergencia")
def emergencia():
    corpo = request.get_json(silent=True) or {}
    acionar = bool(corpo.get("acionar"))
    cfg = carregar_config()
    cfg.emergencia = acionar
    salvar_config(cfg)
    journal.registrar_diario("decisao", f"emergência {'acionada' if acionar else 'liberada'}")
    return jsonify({"emergencia": acionar})


@app.get("/api/consumo")
def consumo():
    return jsonify(budget.consumo_consolidado())


@app.get("/api/limites")
def limites():
    return jsonify(limites_json())


@app.post("/api/sites/autorizar")
def site_autorizar():
    corpo = request.get_json(silent=True) or {}
    dominio = str(corpo.get("dominio", "")).strip().lower()
    if not dominio:
        return jsonify({"erro": "dominio obrigatório"}), 400
    autorizar_dominio(dominio)
    journal.registrar_diario("decisao", f"domínio autorizado: {dominio}")
    return jsonify({"dominios": dominios_autorizados()})


@app.post("/api/sites/remover")
def site_remover():
    corpo = request.get_json(silent=True) or {}
    dominio = str(corpo.get("dominio", "")).strip().lower()
    remover_dominio(dominio)
    journal.registrar_diario("decisao", f"domínio removido: {dominio}")
    return jsonify({"dominios": dominios_autorizados()})


@app.get("/api/sites/acesso_livre")
def site_acesso_livre_status():
    return jsonify({"acesso_livre": acesso_livre()})


@app.post("/api/sites/acesso_livre")
def site_acesso_livre_set():
    corpo = request.get_json(silent=True) or {}
    ativo = bool(corpo.get("ativo"))
    definir_acesso_livre(ativo)
    journal.registrar_diario("decisao", f"acesso livre a sites: {'ativado' if ativo else 'desativado'}")
    return jsonify({"acesso_livre": acesso_livre()})


@app.get("/api/diario")
def diario():
    return jsonify({"diario": journal.diario(ultimos=100)})


@app.get("/api/execucoes")
def execucoes():
    return jsonify({"execucoes": journal.execucoes(ultimos=50)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("AE_API_PORT", "8080")))