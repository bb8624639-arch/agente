"""Contrato Automate Android (webhook HTTPS destilado — inativo no MVP).

Decisão do usuário: começar com Automate usando webhook HTTPS, intents e
notificações (Doogee S100 Pro via app, sem ADB/Appium no MVP).

Este módulo apenas:
- valida payloads que o Automate deve receber;
- fornece funções de montagem de ações (intents, notificações);
- registra no diário quando é chamado (nenhuma execução real no MVP).
"""

from __future__ import annotations

from ..core import journal

ACOES_VALIDAS = frozenset({
    "notificar",            # notificar no aparelho
    "abrir_app",            # intent para abrir app
    "enviar_intent",        # intent arbitrária (valida ação/pacote)
    "ler_dados",            # ler conteúdo de app (futuro)
    "executar_flow",        # executar fluxo Automate predefinido
})


class PayloadInvalido(ValueError):
    pass


def validar_payload(payload: dict) -> dict:
    """Valida estrutura mínima de uma ação Android enviada via webhook.

    Payload esperado:
      {"acao": "notificar", "parametros": {"título": "...", "texto": "..."}}
      {"acao": "abrir_app", "parametros": {"pacote": "com.exemplo.app"}}
      {"acao": "enviar_intent", "parametros": {"acao_intent": "...", "pacote": "..."}}
    """
    acao = payload.get("acao", "")
    parametros = payload.get("parametros", {})
    if acao not in ACOES_VALIDAS:
        raise PayloadInvalido(f"ação desconhecida: {acao}")
    if not isinstance(parametros, dict):
        raise PayloadInvalido("parametros deve ser objeto")
    if acao == "abrir_app" and not parametros.get("pacote"):
        raise PayloadInvalido("abrir_app exige 'pacote'")
    if acao == "enviar_intent" and not parametros.get("acao_intent"):
        raise PayloadInvalido("enviar_intent exige 'acao_intent'")
    return payload


def montar_acao(acao: str, parametros: dict) -> dict:
    return validar_payload({"acao": acao, "parametros": parametros})


def despachar(payload: dict, *, modo: str = "teste") -> dict:
    """Interface real para o Automate (inativo no MVP — só registra).

    Quando for ativado, fará POST HTTPS para o webhook do Automate com os
    campos assinados (a chave de assinatura em env, nunca no código).
    """
    validar_payload(payload)
    journal.registrar_diario(
        "info", "automate_contract (inativo no MVP)",
        {"acao": payload["acao"], "parametros": payload["parametros"], "modo": modo})
    return {"inativo_no_mvp": True, "payload_validado": payload}