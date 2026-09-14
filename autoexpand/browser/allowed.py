"""Allowlist de sites/autorizados e validação de URL.

Regra (não negociável do usuário): qualquer URL fora da allowlist é
**bloqueada** — mesmo em modo autônomo. Um site novo só entra depois de
aprovação humana (entrada na allowlist via painel/API/config).

Rejeita: IPs brutos, localhost, credenciais na URL, protocolos não-https.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from ..config import carregar_config, salvar_config


class SiteNaoAutorizado(Exception):
    def __init__(self, url: str, motivo: str = "fora da allowlist"):
        self.url = url
        self.motivo = motivo
        super().__init__(f"{motivo}: {url}")


class UrlInvalida(Exception):
    pass


def normalizar_dominio(hostname: str) -> str:
    return hostname.strip().lower().rstrip(".")


def dominios_autorizados() -> list[str]:
    return sorted(set(carregar_config().dominio_autorizados))


def autorizar_dominio(dominio: str) -> None:
    cfg = carregar_config()
    dominio = normalizar_dominio(dominio)
    if dominio not in cfg.dominio_autorizados:
        cfg.dominio_autorizados.append(dominio)
        salvar_config(cfg)


def remover_dominio(dominio: str) -> None:
    cfg = carregar_config()
    dominio = normalizar_dominio(dominio)
    cfg.dominio_autorizados = [d for d in cfg.dominio_autorizados if d != dominio]
    salvar_config(cfg)


def _eh_ip(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def validar_url(url: str) -> str:
    """Valida forma; NÃO verifica allowlist (separado). Devolve a URL normalizada."""
    if not isinstance(url, str) or len(url) > 2048:
        raise UrlInvalida("URL muito longa ou inválida")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UrlInvalida("apenas https é permitido")
    if parsed.username or parsed.password:
        raise UrlInvalida("credenciais em URL não são permitidas")
    hostname = parsed.hostname or ""
    if not hostname:
        raise UrlInvalida("hostname ausente")
    if _eh_ip(hostname):
        raise UrlInvalida("IP bruto não é permitido; use domínio")
    if hostname in ("localhost", "127.0.0.1") or hostname.endswith(".local"):
        raise UrlInvalida("localhost/internal não permitido")
    return url


def verificar_autorizada(url: str) -> None:
    """Valida URL e confere allowlist. Levanta SiteNaoAutorizado se fora."""
    try:
        url = validar_url(url)
    except UrlInvalida as exc:
        raise SiteNaoAutorizado(url, str(exc))
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    autorizadas = dominios_autorizados()
    if hostname in autorizadas:
        return
    for dominio in autorizadas:
        if hostname == dominio or hostname.endswith("." + dominio):
            return
    raise SiteNaoAutorizado(url, "site não está na allowlist")


def extrair_urls_de(pedido: str) -> list[str]:
    """Extrai URLs do texto do pedido (https apenas)."""
    return re.findall(r"https://[^\s\"]+", pedido)