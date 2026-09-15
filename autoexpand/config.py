"""Configuração central do sistema.

Todas as constantes de limite moram aqui (um único lugar para auditar).
Valores padrão seguem as diretrizes de economia do usuário.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# config.py vive em <PROJETO>/autoexpand/config.py
PROJETO = Path(__file__).resolve().parent.parent          # /workspace/project
PASTA_ESTADO = Path(os.environ.get("AE_STATE_DIR", PROJETO / "state"))
PASTA_PLUGINS = PROJETO / "autoexpand" / "plugins"
BANCO = PASTA_ESTADO / "orquestrador.db"

# Modos de operação
MODOS = ("teste", "autonomo_controlado", "producao_protegida", "emergencia")
MODO_PADRAO = os.environ.get("AE_MODO", "teste")
MODO_LIVRE_PAGO = ("autonomo_controlado", "producao_protegida")

# Limites econômicos (moeda R$, valores estimados)
LIMITE_MENSAL_IA = float(os.environ.get("AE_LIMITE_MENSAL", "20.0"))
LIMITE_DIARIO_IA = float(os.environ.get("AE_LIMITE_DIARIO", "5.0"))
LIMITE_POR_TAREFA = float(os.environ.get("AE_LIMITE_TAREFA", "2.0"))
MAX_CHAMADAS_IA_POR_TAREFA = int(os.environ.get("AE_MAX_CHAMADAS_IA", "10"))
MAX_TENTATIVAS = int(os.environ.get("AE_MAX_TENTATIVAS", "3"))
TIMEOUT_SCRIPT_S = int(os.environ.get("AE_TIMEOUT_SCRIPT_S", "60"))
MAX_PAGINAS_POR_EXECUCAO = int(os.environ.get("AE_MAX_PAGINAS", "5"))
RECURSAO_PERMITIDA = False

# Jornada do usuário restringe quais chaves são "sempre humanas".
SEMPRE_APROVAR = frozenset({
    "pagamentos", "reembolsos", "pix", "cartao", "contratacao_servicos",
    "credenciais", "exclusao_definitiva", "mensagens_em_massa",
    "publicacao_conteudo", "alteracao_precos", "contato_comercial",
    "contas_terceiros", "fora_da_allowlist", "alterar_regras_seguranca",
    "aumento_orcamento", "publicacao_modulo", "deploy_producao", "envio_mensagem",
})


@dataclass
class Config:
    modo: str = MODO_PADRAO
    dominio_autorizados: list[str] = field(default_factory=list)
    chat_autorizado_telegram: str = ""
    emergencia: bool = False
    aprendizado_idx: int = 0   # posição atual na trilha de estudos infinita

    def caminhos(self) -> Path:
        PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
        return PASTA_ESTADO


def carregar_config() -> Config:
    """Lê config de arquivo (sobrescreve defaults) e mescla com env."""
    cfg = Config()
    PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_ESTADO / "config.json"
    if arquivo.exists():
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dados = {}
        cfg.modo = dados.get("modo", cfg.modo)
        cfg.dominio_autorizados = dados.get("dominios_autorizados", [])
        cfg.chat_autorizado_telegram = dados.get("chat_autorizado_telegram", "")
        cfg.emergencia = bool(dados.get("emergencia", False))
        cfg.aprendizado_idx = int(dados.get("aprendizado_idx", 0) or 0)
    cfg.modo = os.environ.get("AE_MODO", cfg.modo)
    if cfg.modo not in MODOS:
        raise ValueError(f"modo inválido: {cfg.modo!r} (use um de {MODOS})")
    return cfg


def salvar_config(cfg: Config) -> None:
    PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
    dados = {
        "modo": cfg.modo,
        "dominios_autorizados": sorted(set(cfg.dominio_autorizados)),
        "chat_autorizado_telegram": cfg.chat_autorizado_telegram,
        "emergencia": cfg.emergencia,
        "aprendizado_idx": int(getattr(cfg, "aprendizado_idx", 0) or 0),
    }
    (PASTA_ESTADO / "config.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

def _unidade(moeda: str) -> str:
    return {"R$": "reais", "USD": "dólares", "BRL": "reais"}.get(moeda, moeda)


def limites_json() -> dict:
    return {
        "mensal_ia_r": LIMITE_MENSAL_IA, "diario_ia_r": LIMITE_DIARIO_IA,
        "por_tarefa_r": LIMITE_POR_TAREFA,
        "max_chamadas_ia_por_tarefa": MAX_CHAMADAS_IA_POR_TAREFA,
        "max_tentativas": MAX_TENTATIVAS, "timeout_script_s": TIMEOUT_SCRIPT_S,
        "max_paginas_por_execucao": MAX_PAGINAS_POR_EXECUCAO,
        "recursao_permitida": RECURSAO_PERMITIDA,
    }