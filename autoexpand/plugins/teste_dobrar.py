"""Módulo gerado: teste_dobrar.

Gerado pelo Agente Orquestrador — revisado e aprovado antes de publicar.
"""


def executar(entrada: dict) -> dict:
    """Lógica principal. Devolva um dict serializável."""
    return {"dobro": entrada.get("n", 0) * 2}
