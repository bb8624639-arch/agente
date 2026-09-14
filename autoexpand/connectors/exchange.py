"""Conector de câmbio — cotação USD/BRL oficial (PTAX, Banco Central do Brasil).

Fonte pública, sem chave: Olinda BCB. Determinístico (sem LLM).
Usado pelo orquestrador quando o pedido é de cotação/câmbio/dólar.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from typing import TypedDict


class Cotacao(TypedDict):
    compra: float
    venda: float
    data_hora: str
    fonte: str
    url: str


_URL = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='{data}'"
        "&$format=json&$select=cotacaoCompra,cotacaoVenda,dataHoraCotacao")


def _hoje_ptax() -> str:
    """Data de hoje em MM-DD-YYYY (padrão aceito pelo serviço do BCB)."""
    return dt.date.today().strftime("%m-%d-%Y")


def cotacao_dolar_hoje(timeout: int = 15) -> Cotacao | dict:
    """Retorna a cotação PTAX USD/BRL mais recente de hoje.

    Em caso de quota/erro, tenta o dia útil anterior (até 5 tentativas).
    Retorna dict com 'erro' se nenhuma data responder.
    """
    ultimo_erro = None
    for recuo in range(6):
        dia = dt.date.today() - dt.timedelta(days=recuo)
        data = dia.strftime("%m-%d-%Y")
        url = _URL.format(data=data)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
            valores = payload.get("value") or []
            if valores:
                item = valores[0]
                return {
                    "compra": item["cotacaoCompra"],
                    "venda": item["cotacaoVenda"],
                    "data_hora": item["dataHoraCotacao"],
                    "fonte": "PTAX · Banco Central do Brasil",
                    "url": "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/",
                    "dados_de": dia.isoformat(),
                }
        except Exception as exc:  # quota, rede, JSON — tenta dia anterior
            ultimo_erro = exc
    return {"erro": f"não foi possível obter cotação (BCB indisponível): {ultimo_erro}"}


def formatar_cotacao(cot: Cotacao | dict) -> str:
    """Monta mensagem curta para o Telegram/painel."""
    if "erro" in cot:
        return f"❌ {cot['erro']}"
    return (
        f"💵 *Dólar (PTAX / BCB)*\n"
        f"Compra: R$ {cot['compra']:.4f}\n"
        f"Venda:  R$ {cot['venda']:.4f}\n"
        f"Fonte: {cot.get('fonte','')} · {cot.get('data_hora','')}\n"
        f"Dados de {cot.get('dados_de','')}"
    )