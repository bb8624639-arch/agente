"""Executor isolado por subprocesso com limites rígidos.

Cada execução roda em um processo separado (isolamento de memória e de
falhas), com timeouts e limites de memória forçados:
- Python: `resource.setrlimit` (CPU, memória) + faixa de |
- JavaScript: flag `--max-old-space-size` do Node

APIs de rede **não** são bloqueadas aqui: o *enforcement* de
permissões de rede é feito na camada de permissões do registro, por
meio do pacote de permissões concedido ao runtime. Este módulo garante
apenas isolamento/limites de recursos.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .permissions import NOMES


class ErroSandbox(Exception):
    """Erro de sandbox: timeout, estouro de memória, sinal, etc."""


@dataclass
class PacotePermissao:
    """Permissões efetivamente concedidas a uma execução."""
    permitidas: set[str]
    denied: set[str] = field(default_factory=set)

    @classmethod
    def do_manifesto(cls, permissoes: list[str], permitidas_globais: set[str] | None = None) -> "PacotePermissao":
        globais = permitidas_globais if permitidas_globais is not None else set()
        for p in permissoes:
            if p not in NOMES:
                raise ErroSandbox(f"permissão desconhecida: {p}")
        negadas = set(permissoes) - globais
        return cls(permitidas=set(permissoes) & globais, denied=negadas)

    def to_dict(self) -> dict[str, Any]:
        return {"permitidas": sorted(self.permitidas), "negadas": sorted(self.denied)}


def _prolog_python() -> str:
    return (
        "import json, os, sys\n"
        "def __carregar_saida():\n"
        "    _p = os.environ.get('AE_INPUT_JSON')\n"
        "    return json.loads(_p) if _p else json.load(sys.stdin)\n"
        "def __escrever_saida(_v):\n"
        "    with open(os.environ.get('AE_OUTPUT_JSON', '/tmp/ae_out.json'), 'w') as _f:\n"
        "        json.dump(_v, _f, ensure_ascii=False)\n"
        "        _f.flush()\n"
        "        os.fsync(_f.fileno())\n"
        "try:\n"
        "    __entrada = __carregar_saida()\n"
        "except Exception:\n"
        "    __entrada = {}\n"
        "def entrada():\n"
        "    return __entrada\n"
        "def saida(_v):\n"
        "    __escrever_saida(_v)\n"
        "    return _v\n"
    )


def _prolog_js() -> str:
    return (
        "const fs = require('fs');\n"
        "let __entrada = {};\n"
        "try {\n"
        "  const _raw = process.env.AE_INPUT_JSON ?? fs.readFileSync(0, 'utf8');\n"
        "  __entrada = JSON.parse(_raw || '{}');\n"
        "} catch (_e) { __entrada = {}; }\n"
        "global.entrada = () => JSON.parse(JSON.stringify(__entrada));\n"
        "global.saida = (v) => { "
        "fs.writeFileSync(process.env.AE_OUTPUT_JSON || '/tmp/ae_out.json', JSON.stringify(v)); "
        "return v; };\n"
    )


RLIMIT_DEFAULT = {
    "nofile": 64,       # arquivos abertos
    "nproc": 64,        # processos filhos
}


def executar_python(codigo: str, entrada: dict, timeout: float, memoria_mb: int,
                    working_dir: str | None = None) -> dict[str, Any]:
    """Executa código Python isolado. Retorna {"ok": bool, "resultado": ..., "erro": ...}."""
    prefixo = _prolog_python()
    if codigo.startswith("def ") or codigo.startswith("def"):
        prefixo += "def main():\n"
    codigo_final = prefixo + codigo
    saida = os.path.join(tempfile.mkdtemp(prefix="ae_sandbox_"), "out.json")
    env = dict(os.environ, AE_INPUT_JSON=json.dumps(entrada),
               AE_OUTPUT_JSON=saida, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen(
        [sys.executable, "-c", codigo_final],
        env=env,
        cwd=working_dir or "/",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=_limites_processo(timeout, memoria_mb),
    )
    try:
        stdout, stderr = proc.communicate(json.dumps(entrada), timeout=timeout + 2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return {"ok": False, "resultado": None,
                "erro": f"timeout de {timeout:g}s excedido",
                "saida": _ultimo_trecho(saida)}
    if proc.returncode != 0:
        return {"ok": False, "resultado": None,
                "erro": _erro_humano(proc.returncode, stderr),
                "stderr": stderr[-2000:]}
    try:
        with open(saida, encoding="utf-8") as f:
            resultado = json.load(f)
    except FileNotFoundError:
        resultado = {"texto": stdout.strip()[-2000:]}
    except json.JSONDecodeError:
        resultado = {"texto": stdout.strip()[-2000:]}
    return {"ok": True, "resultado": resultado, "stderr": stderr[-2000:]}


def _limites_processo(timeout: float, memoria_mb: int):
    def _aplicar():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (max(int(timeout), 1), max(int(timeout), 1) + 1))
            resource.setrlimit(resource.RLIMIT_AS,
                               (memoria_mb * 1024 * 1024, memoria_mb * 1024 * 1024))
            for nome, limite in RLIMIT_DEFAULT.items():
                recurso = getattr(resource, f"RLIMIT_{nome.upper()}", None)
                if recurso is not None:
                    try:
                        resource.setrlimit(recurso, (limite, limite))
                    except (ValueError, OSError):
                        pass
            if hasattr(os, "setsid"):
                os.setsid()
        except Exception:
            pass
    return _aplicar


def _erro_humano(codigo: int, stderr: str) -> str:
    sinal = -codigo
    if sinal == 9:
        return "memória estourada (estourou o limite do sandbox)"
    print(stderr.strip()[-2000:] or f"código de saída {codigo}")
    if sinal == 24:
        return "limite de processos alcançado"
    return (stderr.strip()[-2000:] or f"código de saída {codigo}")


def _ultimo_trecho(caminho: str) -> str:
    try:
        with open(caminho, encoding="utf-8") as f:
            return f.read()[-2000:]
    except FileNotFoundError:
        return ""


def executar_javascript(codigo: str, entrada: dict, timeout: float, memoria_mb: int,
                        working_dir: str | None = None) -> dict[str, Any]:
    """Executa código JavaScript com Node.js. Retorna {"ok": bool, ...}."""
    prefixo = _prolog_js()
    codigo_final = prefixo + codigo
    saida = os.path.join(tempfile.mkdtemp(prefix="ae_sandbox_js_"), "out.json")
    env = dict(os.environ, AE_INPUT_JSON=json.dumps(entrada),
               AE_OUTPUT_JSON=saida)
    proc = subprocess.Popen(
        ["node", f"--max-old-space-size={memoria_mb}", "-e", codigo_final],
        env=env, cwd=working_dir or "/",
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(json.dumps(entrada), timeout=timeout + 2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return {"ok": False, "resultado": None, "erro": f"timeout de {timeout:g}s excedido"}
    if proc.returncode != 0:
        return {"ok": False, "resultado": None,
                "erro": (stderr or stdout).strip()[-2000:] or f"código de saída {proc.returncode}"}
    try:
        with open(saida, encoding="utf-8") as f:
            resultado = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        resultado = {"fim": stdout.strip()[-2000:]}
    return {"ok": True, "resultado": resultado}


def executar(codigo: str, lingua: str, entrada: dict, *, timeout: float = 30,
             memoria_mb: int = 128, working_dir: str | None = None) -> dict[str, Any]:
    """Dispara execução na língua apropriada com limites dados."""
    if lingua == "python":
        return executar_python(codigo, entrada, timeout, memoria_mb, working_dir)
    if lingua == "javascript":
        return executar_javascript(codigo, entrada, timeout, memoria_mb, working_dir)
    raise ErroSandbox(f"runtime não suportado para execução: {lingua}")