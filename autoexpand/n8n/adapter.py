"""Adaptador n8n (contrato + mock; sem conexão real no MVP).

Preparado para REST API do n8n via env:
  N8N_URL, N8N_API_KEY
Sem credenciais: devolve um mock marcado, para que o fluxo se integre sem
bloquear o desenvolvimento. Nunca loga credenciais.

`criar_workflow(nome, nos, credencial_ref)` monta o payload JSON do n8n.
Além disso, expõe uma interface de integração via webhook (quando o n8n
estiver conectado, envie para N8N_URL/webhook/<path>).
"""

from __future__ import annotations

import json
import os

from ..core import journal

N8N_URL = os.environ.get("N8N_URL", "")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
CONECTADO = bool(N8N_URL and N8N_API_KEY)


class N8nNaoConectado(Exception):
    pass


def montar_payload(nome: str, nos: list[dict], credencial_ref: str = "") -> dict:
    """Monta payload JSON de workflow n8n (mínimo viável p/ import).

    `nos` = lista de {id, tipo (ex.: n8n-nodes-base.httpRequest),
                      parametros: {...}, posicao: [x, y]}.
    Credenciais são referências (ex.: `env:GITHUB_TOKEN`), nunca valores.
    """
    return {
        "name": nome,
        "nodes": nos,
        "connections": {},
        "settings": {"executionOrder": "v1"},
        "credentials": json.loads(credencial_ref) if credencial_ref else {},
    }


def criar_workflow(nome: str, nos: list[dict], credencial_ref: str = "") -> dict:
    """Cria workflow no n8n. Sem env → mock (modo teste/economia)."""
    payload = montar_payload(nome, nos, credencial_ref)
    if not CONECTADO:
        journal.registrar_diario(
            "info", "n8n mock (sem credenciais)",
            {"nome": nome, "qtd_nos": len(nos)})
        return {"mock": True, "workflow": payload,
                "aviso": "n8n não conectado: payload retornado para inspeção"}
    import requests
    resp = requests.post(
        N8N_URL.rstrip("/") + "/api/v1/workflows",
        headers={"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"},
        json=payload, timeout=30)
    resp.raise_for_status()
    return {"mock": False, "workflow": resp.json()}


def webhook_payload(nos: list[dict], path: str, metodo: str = "POST") -> list[dict]:
    """Helper: adiciona nó de webhook no início do workflow p/ integração."""
    return [
        {"id": "wh-1", "type": "n8n-nodes-base.webhook",
         "parametros": {"httpMethod": metodo, "path": path}, "posicao": [0, 0]},
        *nos,
    ]