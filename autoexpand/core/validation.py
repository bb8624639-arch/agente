"""Validação de parâmetros de entrada e conformidade de saída.

Schema suporta o subconjunto mais útil de JSON Schema:
type, required, enum, min/max (number/string), pattern (string),
items (array), properties/required (object) e additionalProperties.
Sem IA: validação determinística e barata, rodando antes de qualquer LLM.
"""

import re


class ErroValidacao(ValueError):
    """Falha de validação de entrada ou saída."""


_TIPOS = {"string", "integer", "number", "boolean", "object", "array", "null"}


def _tipo(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, int):
        return "integer"
    if isinstance(valor, float):
        return "number"
    if isinstance(valor, str):
        return "string"
    if isinstance(valor, list):
        return "array"
    if isinstance(valor, dict):
        return "object"
    return type(valor).__name__


def _erro(caminho: str, msg: str):
    raise ErroValidacao(f"{caminho}: {msg}" if caminho else msg)


def validar_valor(schema: dict, valor, caminho: str = "") -> None:
    tipo = schema.get("type")
    if tipo:
        if tipo not in _TIPOS:
            _erro(caminho, f"tipo desconhecido: {tipo}")
        if _tipo(valor) != tipo:
            _erro(caminho, f"esperado {tipo}, obtido {_tipo(valor)}")

    if valor is None:
        return

    if isinstance(valor, str):
        if "minLength" in schema and len(valor) < schema["minLength"]:
            _erro(caminho, f"tamanho mínimo {schema['minLength']}")
        if "maxLength" in schema and len(valor) > schema["maxLength"]:
            _erro(caminho, f"tamanho máximo {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], valor):
            _erro(caminho, f"não casa com pattern {schema['pattern']}")
    elif isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if "minimum" in schema and valor < schema["minimum"]:
            _erro(caminho, f"abaixo de minimum={schema['minimum']}")
        if "maximum" in schema and valor > schema["maximum"]:
            _erro(caminho, f"acima de maximum={schema['maximum']}")
    elif isinstance(valor, list):
        if "minItems" in schema and len(valor) < schema["minItems"]:
            _erro(caminho, f"minItems={schema['minItems']}")
        if "maxItems" in schema and len(valor) > schema["maxItems"]:
            _erro(caminho, f"maxItems={schema['maxItems']}")
        for i, item in enumerate(valor):
            if "items" in schema:
                validar_valor(schema["items"], item, f"{caminho}[{i}]")
    elif isinstance(valor, dict):
        for nome_prop, sub in schema.get("properties", {}).items():
            if nome_prop in valor:
                validar_valor(sub, valor[nome_prop], f"{caminho}.{nome_prop}")
        for req in schema.get("required", []):
            if req not in valor:
                _erro(caminho, f"propriedade obrigatória ausente: {req}")
        if not schema.get("additionalProperties", True):
            extras = set(valor) - set(schema.get("properties", {}))
            if extras:
                _erro(caminho, f"propriedades não permitidas: {sorted(extras)}")

    if "enum" in schema and valor not in schema["enum"]:
        _erro(caminho, f"valor fora do enum: {valor!r}")


def validar_params(schema: dict, params: dict) -> dict:
    if not schema:
        if params:
            raise ErroValidacao("não são aceitos parâmetros (schema vazio)")
        return {}
    if not isinstance(params, dict):
        raise ErroValidacao("parâmetros devem ser um objeto")
    schema_n = {"type": "object", **schema}
    validar_valor(schema_n, params, "$")
    for req in schema.get("required", []):
        if req not in params:
            raise ErroValidacao(f"$: propriedade obrigatória ausente: {req}")
    return params


def validar_saida(schema: dict, saida) -> None:
    if not schema:
        return
    validar_valor({"type": "object", **schema}, saida, "$")