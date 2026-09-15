"""Adaptador de LLM independente de provedor.

Interface única para o resto do sistema. O provedor real é selecionado por env:
AE_LLM_BASE_URL (formato OpenAI-compatible), AE_LLM_API_KEY, AE_LLM_MODEL_BARATO,
AE_LLM_MODEL_AVANCADO. Sem chave → `disponivel()==False` e todas as funções caem
em regras/templates determinísticos (economia de créditos).

Nenhuma credencial é logada: os pedidos/respostas registrados via journal são
só métricas (contagem/tokens) — sem conteúdo.

Funções de classificação/extração/roteamento usam o modelo barato configurado;
planejamento/geração de código/diagnóstico difícil usam o avançado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..core import budget, journal

BASE_URL = os.environ.get("AE_LLM_BASE_URL", "")
API_KEY = os.environ.get("AE_LLM_API_KEY", "")
MODELO_BARATO = os.environ.get("AE_LLM_MODEL_BARATO", "gemini-2.0-flash")
MODELO_AVANCADO = os.environ.get("AE_LLM_MODEL_AVANCADO", "gpt-4o-mini")
PROVEDOR_ATUAL = os.environ.get("AE_LLM_PROVIDER", "")
TEM_LLM = bool(BASE_URL and API_KEY)

# Catálogo de provedores aceitos. Tipo "openai" = formato /chat/completions;
# tipo "openhands" = API do All Hands (conversas V1, auth Bearer). O nome do
# provedor é resolvido por slug no /set_api do Telegram.
PROVEDORES: dict[str, dict] = {
    "gemini": {
        "nome": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "modelo_barato": "gemini-2.0-flash",
        "modelo_avancado": "gemini-2.0-flash",
        "tipo": "openai",
    },
    "openai": {
        "nome": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "modelo_barato": "gpt-4o-mini",
        "modelo_avancado": "gpt-4o-mini",
        "tipo": "openai",
    },
    "openrouter": {
        "nome": "OpenRouter (vários modelos)",
        "base_url": "https://openrouter.ai/api/v1",
        "modelo_barato": "meta-llama/llama-3.3-70b-instruct",
        "modelo_avancado": "anthropic/claude-3.5-sonnet",
        "tipo": "openai",
    },
    "groq": {
        "nome": "Groq (rápido e grátis)",
        "base_url": "https://api.groq.com/openai/v1",
        "modelo_barato": "llama-3.3-70b-versatile",
        "modelo_avancado": "llama-3.3-70b-versatile",
        "tipo": "openai",
    },
    "deepseek": {
        "nome": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "modelo_barato": "deepseek-chat",
        "modelo_avancado": "deepseek-chat",
        "tipo": "openai",
    },
    "local": {
        "nome": "Local / Ollama (OpenAI-compatível)",
        "base_url": "http://localhost:11434/v1",
        "modelo_barato": "llama3",
        "modelo_avancado": "llama3",
        "tipo": "openai",
    },
    "openhands": {
        "nome": "All Hands (OpenHands Cloud)",
        "base_url": "https://app.all-hands.dev",
        "modelo_barato": "",
        "modelo_avancado": "",
        "tipo": "openhands",
    },
}


def info_provedor(slug: str) -> dict | None:
    """Retorna o catálogo de um provedor (ou None se não existir)."""
    slug = _normalizar_provedor(slug)
    return PROVEDORES.get(slug)

PROVEDORES_POR_SLUG = PROVEDORES

# Sinônimos para os slugs do catálogo (aceitos no /set_api).
_SINONIMOS = {
    "allhands": "openhands",
    "all_hands": "openhands",
    "all-hands": "openhands",
    "oh": "openhands",
    "google": "gemini",
    "googleai": "gemini",
    "ollama": "local",
    "grok": "groq",
}


def _normalizar_provedor(provedor: str) -> str:
    """Normaliza o nome do provedor (case, sinônimos)."""
    p = (provedor or "").strip().lower().replace(" ", "_")
    return _SINONIMOS.get(p, p)

# Custo estimado por milháo de tokens (R$), por modelo (para o journal).
# Valores conservadores/ajustáveis — usados apenas p/ contabilizar estimativa.
CUSTO_POR_MILHAO: dict[str, float] = {
    "gemini-2.0-flash": 0.80,   # barato (classificação)
    "gpt-4o-mini": 2.50,        # avançado (planejamento/geração)
}
CUSTO_PADRAO_BARATO = 1.0
CUSTO_PADRAO_AVANCADO = 3.0


@dataclass
class ChamadaLLM:
    modelo: str
    motivo: str
    prompt_reduzido_caracteres: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_r: float = 0.0
    resposta: str = ""
    erro: str = ""


def _estimar_tokens(texto: str) -> int:
    # heurística barata (~4 chars/token), suficiente p/ estimativas
    return max(1, len(texto) // 4)


def _custo_por_milhao(modelo: str) -> float:
    return CUSTO_POR_MILHAO.get(modelo, CUSTO_PADRAO_BARATO)


def _tipo_atual() -> str:
    """Tipo do provedor ativo (openai/openhands), resolvido pelo slug salvo."""
    prov = PROVEDORES.get(PROVEDOR_ATUAL)
    if not prov:
        prov = PROVEDORES.get(os.environ.get("AE_LLM_PROVIDER", ""))
    return (prov or {}).get("tipo", "openai")


def _chamar_openai(prompt: str, modelo: str, motivo: str,
                   temperatura: float = 0.0, max_saida: int = 2000) -> ChamadaLLM:
    import json
    import urllib.request

    body = json.dumps({
        "model": modelo, "temperature": temperatura,
        "max_tokens": max_saida,
        "messages": [{"role": "user", "content": prompt[:16000]}]  # contexto reduzido
    }).encode()
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/chat/completions",
                                 data=body)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        dados = json.load(resp)
    texto = dados["choices"][0]["message"]["content"] or ""
    tokens_entrada = int(dados.get("usage", {}).get("prompt_tokens",
                                                    _estimar_tokens(prompt[:16000])))
    tokens_saida = int(dados.get("usage", {}).get("completion_tokens",
                                                  _estimar_tokens(texto)))
    return texto, tokens_entrada, tokens_saida


def _extrair_msg(msg) -> str:
    """Extrai texto de uma mensagem do OpenHands (content lista | str | dict).

    O Cloud usa `llm_message.content[].text`; local usa `message.content`. Em
    caso de empate, prefere `llm_message`.
    """
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        partes = []
        for p in msg:
            if isinstance(p, str):
                partes.append(p)
            elif isinstance(p, dict):
                if p.get("type") in ("text", "content", "output") and p.get("text"):
                    partes.append(str(p["text"]))
                elif p.get("text"):
                    partes.append(str(p["text"]))
        return "\n".join(partes)
    if isinstance(msg, dict):
        if msg.get("llm_message"):
            return _extrair_msg(msg["llm_message"])
        if msg.get("message"):
            return _extrair_msg(msg["message"])
        if msg.get("content"):
            return _extrair_msg(msg["content"])
        if msg.get("text"):
            return _extrair_msg(msg["text"])
        for k in ("value",):
            if msg.get(k):
                return _extrair_msg(msg[k])
    return ""


def _chamar_openhands(prompt: str, max_saida: int = 2000) -> ChamadaLLM:
    """Usa a API V1 do All Hands/OpenHands Cloud (conversas, auth Bearer).

    O All Hands não expõe /chat/completions; ele agenda uma conversa que roda
    em sandbox e consome a mensagem inicial com tools. Esta implementação:
      1. POST /api/v1/app-conversations com a mensagem inicial (run);
      2. aguarda o READY da start-task (polling curto);
      3. lê os eventos da conversa e devolve o último texto do assistant.
    Em erro, devolve a mensagem de erro (sem credencial).
    """
    import json
    import time as _time
    import urllib.request

    base = BASE_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {API_KEY}",
               "Content-Type": "application/json"}

    def _post(url, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body)
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)

    def _get(url) -> dict:
        req = urllib.request.Request(url)
        req.add_header("Authorization", headers["Authorization"])
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    # 1. inicia a conversa
    start = _post(base + "/api/v1/app-conversations", {
        "initial_message": {
            "content": [{"type": "text", "text": prompt[:8000]}],
            "run": True,
        },
    })
    app_id = start.get("app_conversation_id")
    start_id = start.get("id")
    if not app_id and start_id:
        # polling da start-task até READY (resposta pode ser lista)
        for _ in range(30):
            _time.sleep(2)
            try:
                estado = _get(
                    f"{base}/api/v1/app-conversations/start-tasks?ids={start_id}")
            except Exception:
                estado = {}
            itens = estado if isinstance(estado, list) else (
                estado.get("start_tasks") or estado.get("items") or [estado])
            app_id = next((it.get("app_conversation_id") for it in itens
                           if it.get("app_conversation_id")), None)
            if app_id:
                break
    if not app_id:
        return "erro: All Hands não retornou id de conversa", 0, 0

    # 2. aguarda a conversa terminar e lê a última resposta do assistant
    for _ in range(40):
        _time.sleep(3)
        try:
            url = (f"{base}/api/v1/conversation/{app_id}/events/search?"
                   f"limit=50&sort_order=TIMESTAMP_DESC")
            req = urllib.request.Request(url)
            for k, v in headers.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=30) as resp:
                dados = json.load(resp)
        except Exception:
            continue
        itens = dados.get("items", [])
        terminou = any(
            ev.get("kind") == "ConversationStateUpdateEvent"
            and ev.get("key") == "execution_status"
            and str(ev.get("value", "")).lower() in ("finished", "stopped", "error", "aborted")
            for ev in itens)
        texto_final = ""
        for ev in itens:
            if ev.get("source") in ("assistant", "agent") and ev.get("kind") == "MessageEvent":
                t = _extrair_msg(ev)
                if t.strip():
                    texto_final = t
        if texto_final.strip():
            return texto_final.strip(), 0, len(texto_final) // 4
        if terminou and not texto_final.strip():
            return "erro: All Hands terminou sem resposta textual", 0, 0
    return "erro: timeout aguardando resposta do All Hands", 0, 0


def _chamar(prompt: str, modelo: str, motivo: str, temperatura: float = 0.0,
            max_saida: int = 2000) -> ChamadaLLM:
    """Faz chamada real (se habilitada) ou devolve resposta vazia (modo sem IA)."""
    registro = ChamadaLLM(modelo=modelo, motivo=motivo)
    if not TEM_LLM:
        registro.resposta = ""
        return registro

    try:
        if _tipo_atual() == "openhands":
            texto, tin, tout = _chamar_openhands(prompt, max_saida)
        else:
            texto, tin, tout = _chamar_openai(prompt, modelo, motivo,
                                              temperatura, max_saida)
    except Exception as exc:  # rede/auth/rate limit → não quebra o pipeline
        texto = f"erro: {str(exc)[:300]}"
        tin = _estimar_tokens(prompt[:16000])
        tout = 0
    registro.tokens_entrada = tin
    registro.tokens_saida = tout
    registro.resposta = texto if not texto.startswith("erro:") else ""
    registro.erro = texto if texto.startswith("erro:") else ""
    _registrar_consumo(registro, motivo)
    return registro


def _registrar_consumo(llamada: ChamadaLLM, motivo: str) -> None:
    custo = ((llamada.tokens_entrada + llamada.tokens_saida) / 1_000_000) * \
        _custo_por_milhao(llamada.modelo)
    llamada.custo_r = custo
    budget.registrar_uso(chamadas_ia=1, tokens_in=llamada.tokens_entrada,
                         tokens_out=llamada.tokens_saida, custo_r=custo)
    journal.registrar_diario("info", "chamada LLM",
                             {"modelo": llamada.modelo, "motivo": motivo,
                              "tokens_in": llamada.tokens_entrada,
                              "tokens_out": llamada.tokens_saida,
                              "custo_r": round(custo, 4)})


def reconfigurar(*, provider: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, modelo_barato: str | None = None,
                 modelo_avancado: str | None = None) -> bool:
    """Atualiza a configuração do LLM em runtime (sem reiniciar o bot).

    Usada pelo comando `/set_api` do Telegram. Passar None mantém o atual;
    passe string vazia para limpar (desabilita o LLM).

    Se `provider` for um slug do catálogo PROVEDORES, preenche base_url e
    modelos automaticamente (ex.: "gemini", "openai", "openhands").
    """
    global BASE_URL, API_KEY, MODELO_BARATO, MODELO_AVANCADO, PROVEDOR_ATUAL, TEM_LLM

    provider = _normalizar_provedor(provider) if provider is not None else None
    if provider is not None:
        PROVEDOR_ATUAL = provider
        os.environ["AE_LLM_PROVIDER"] = provider
    if prov := PROVEDORES.get(provider or ""):
        base_url = base_url or prov["base_url"]
        if not modelo_barato and prov.get("modelo_barato"):
            modelo_barato = prov["modelo_barato"]
        if not modelo_avancado and prov.get("modelo_avancado"):
            modelo_avancado = prov["modelo_avancado"]
    if base_url is not None:
        BASE_URL = base_url
        os.environ["AE_LLM_BASE_URL"] = base_url
    if api_key is not None:
        API_KEY = api_key
        os.environ["AE_LLM_API_KEY"] = api_key
    if modelo_barato is not None:
        MODELO_BARATO = modelo_barato
        os.environ["AE_LLM_MODEL_BARATO"] = modelo_barato
    if modelo_avancado is not None:
        MODELO_AVANCADO = modelo_avancado
        os.environ["AE_LLM_MODEL_AVANCADO"] = modelo_avancado
    TEM_LLM = bool(BASE_URL and API_KEY)
    return TEM_LLM


def testar_conexao() -> tuple[bool, str]:
    """Faz uma chamada mínima para verificar se a API está acessível.

    Retorna (ok, detalhe). Sem config, retorna (False, "sem LLM configurado").
    """
    if not TEM_LLM:
        return False, "nenhuma API LLM configurada (use /set_api)"
    nome_prov = PROVEDORES.get(PROVEDOR_ATUAL, {}).get("nome", MODELO_BARATO)
    try:
        r = barato("Responda apenas: ok", "teste de conexão", max_saida=20)
        if r.strip():
            modelo_uso = MODELO_BARATO if _tipo_atual() != "openhands" else "openhands"
            return True, f"conectado via {nome_prov} ({modelo_uso})"
        return False, "API respondeu vazio — verifique a chave/modelo"
    except Exception as exc:
        return False, f"erro de conexão: {str(exc)[:200]}"


def barato(prompt: str, motivo: str, *, max_saida: int = 500) -> str:
    """Modelo econômico: classificação, extração, roteamento, decisões simples."""
    chamada = _chamar(prompt, MODELO_BARATO, motivo, temperatura=0.0, max_saida=max_saida)
    return chamada.resposta


def avancado(prompt: str, motivo: str, *, max_saida: int = 3000) -> str:
    """Modelo avançado: planejamento complexo, geração de código, diagnóstico."""
    chamada = _chamar(prompt, MODELO_AVANCADO, motivo, temperatura=0.2, max_saida=max_saida)
    return chamada.resposta


def disponivel() -> bool:
    return TEM_LLM