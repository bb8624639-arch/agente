"""Manifesto dos módulos: schema explícito e validações.

Cada módulo declara permissões, tempo esgotado, limite de memória, schemas
de entrada/saída e política de aprovação. Nenhuma permissão pode ser
auto-concedida — a lista abaixo de `permissoes` é o teto do que o script
pode pedir ao runtime, e o registratório confere antes de publicar.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from .permissions import TODOS

RUNTIMES = frozenset({"python", "javascript", "typescript", "shell"})

CAMPO_OBRIGATORIO = """manifesto inválido: {campo} é obrigatório"""


class SchemaInvalido(ValueError):
    """Erro de validação de manifesto ou parâmetros."""


def _validar_campos(m: dict) -> dict:
    faltando = [c for c in ("nome", "versao", "perfil", "permissoes",
                            "input_schema", "output_schema") if c not in m]
    if faltando:
        raise SchemaInvalido("campos obrigatórios ausentes: " + ", ".join(faltando))
    if not isinstance(m["nome"], str) or not m["nome"].strip():
        raise SchemaInvalido(CAMPO_OBRIGATORIO.format(campo="nome"))
    if not isinstance(m["versao"], str):
        raise SchemaInvalido("versao deve ser string (semver)")
    if not isinstance(m["perfil"], str):
        raise SchemaInvalido("perfil deve ser string (rascunho | publicado)")
    if m["perfil"] not in ("rascunho", "publicado"):
        raise SchemaInvalido("perfil deve ser rascunho ou publicado")
    if not isinstance(m["permissoes"], list):
        raise SchemaInvalido("permissoes deve ser lista")
    desconhecidas = set(m["permissoes"]) - TODOS
    if desconhecidas:
        raise SchemaInvalido("permissões desconhecidas: " + ", ".join(sorted(desconhecidas)))
    for chave, schema in (("input_schema", m["input_schema"]),
                          ("output_schema", m["output_schema"])):
        if not isinstance(schema, dict):
            raise SchemaInvalido(f"{chave} deve ser um dicionário")
    return m


def normalizar_manifesto(entrada: dict) -> dict:
    """Transforma o formato humano (nome/versão/"requer_aprovação":falso)
    no formato canônico do registro."""
    ent = {k: v for k, v in entrada.items()}
    ent["nome"] = ent.get("nome") or ent.get("name", "")
    if "versao" not in ent and "versão" in ent:
        ent["versao"] = ent["versão"]
    if "versao" not in ent:
        ent["versao"] = ent.get("version", "1.0.0")
    ent["perfil"] = ent.get("perfil", "rascunho")
    ent.setdefault("runtime", "python")
    ent.setdefault("timeout_seconds", 30)
    ent.setdefault("limite_memoria_mb", 128)
    ent.setdefault("script", {})
    ent.setdefault("tolerancia_falhas", 3)
    ent.setdefault("monitorado", False)
    ent.setdefault("aprovado", False)
    _validar_campos(ent)
    if ent["runtime"] not in RUNTIMES:
        raise SchemaInvalido("runtime não suportado: " + str(ent["runtime"]))
    if (isinstance(ent["timeout_seconds"], bool) or
            not isinstance(ent["timeout_seconds"], int) or
            not (1 <= ent["timeout_seconds"] <= 3600)):
        raise SchemaInvalido("timeout_seconds inválido: 1..3600")
    if (isinstance(ent["limite_memoria_mb"], bool) or
            not isinstance(ent["limite_memoria_mb"], int) or
            not (8 <= ent["limite_memoria_mb"] <= 2048)):
        raise SchemaInvalido("limite_memoria_mb inválido: 8..2048")
    # Não ler script em execução (security): apenas "lingua" do script.
    if not isinstance(ent["script"], dict):
        raise SchemaInvalido("script deve ser um dicionário {lingua: código}")
    for lingua, codigo in ent["script"].items():
        if lingua not in ("python", "javascript"):
            raise SchemaInvalido("lingua não suportada no script: " + str(lingua))
        if not isinstance(codigo, str):
            raise SchemaInvalido("código do script deve ser string")
    return ent


@dataclass
class Modulo:
    nome: str
    versao: str
    perfil: str                       # rascunho | publicado
    description: str
    runtime: str
    permissoes: list[str] = field(default_factory=list)
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    timeout_seconds: int = 30
    limite_memoria_mb: int = 128
    tolerancia_falhas: int = 3
    script: dict = field(default_factory=dict, repr=False)
    aprovado: bool = False
    monitorado: bool = False
    hash: str = ""
    registrado_em: float = field(default_factory=time.time)

    @classmethod
    def de_manifesto(cls, entrada: dict) -> "Modulo":
        m = normalizar_manifesto(entrada)
        return cls(**m)


def validar_params(com_schema: dict, params_alvo: dict) -> dict:
    """Valida parâmetros de entrada contra um schema estilo JSON Schema.

    Suportado: type (string|integer|number|boolean|object|array),
    required, enum, min/max, pattern básico, nested object.
    """
    from .validation import validar_params  # circular-safe
    return validar_params(com_schema, params_alvo)