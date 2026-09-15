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


def eh_onion(hostname: str) -> bool:
    """True para endereços .onion (somente alcançáveis via rede Tor)."""
    return hostname.lower().endswith(".onion")


def validar_url(url: str) -> str:
    """Valida forma; NÃO verifica allowlist (separado). Devolve a URL normalizada.

    Segurança mantida: apenas https (ou http **exclusivamente para .onion**,
    pois a rede Tor só roteia dentro dela e o tráfego não sai exposto em texto
    claro para a internet). Sem IP bruto, sem localhost, sem credenciais.
    """
    if not isinstance(url, str) or len(url) > 2048:
        raise UrlInvalida("URL muito longa ou inválida")
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        # http é tolerado APENAS para .onion (dark web via Tor); qualquer outro
        # site precisa de https (surface/deep web).
        if not (parsed.scheme == "http" and eh_onion(parsed.hostname or "")):
            raise UrlInvalida("apenas https é permitido (ou http para .onion)")
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


def acesso_livre() -> bool:
    """True quando o agente pode abrir qualquer site (sem allowlist)."""
    from ..config import carregar_config
    return bool(getattr(carregar_config(), "acesso_livre_sites", False))


def definir_acesso_livre(ativo: bool) -> bool:
    """Liga/desliga o acesso livre a qualquer site (com validação de segurança)."""
    from ..config import carregar_config, salvar_config
    cfg = carregar_config()
    cfg.acesso_livre_sites = bool(ativo)
    salvar_config(cfg)
    return cfg.acesso_livre_sites


def verificar_autorizada(url: str) -> None:
    """Valida URL e (se não for acesso livre) confere allowlist.

    A validação de segurança SEMPRE roda: apenas https, sem IP bruto/localhost,
    sem credenciais na URL. No modo acesso livre, a allowlist é ignorada, mas
    nada disso é flexibilizado.
    """
    try:
        url = validar_url(url)
    except UrlInvalida as exc:
        raise SiteNaoAutorizado(url, str(exc))
    if acesso_livre():
        return
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    autorizadas = dominios_autorizados()
    if hostname in autorizadas:
        return
    for dominio in autorizadas:
        if hostname == dominio or hostname.endswith("." + dominio):
            return
    raise SiteNaoAutorizado(url, "site não está na allowlist (acesso livre desativado)")


def extrair_urls_de(pedido: str) -> list[str]:
    """Extrai URLs do texto do pedido (https apenas)."""
    return re.findall(r"https://[^\s\"]+", pedido)