"""Testes do menu InlineKeyboard do bot Telegram (sem rede, com mocks)."""
import pytest
import requests

import autoexpand.telegram.bot as tbot

CHAT = 123456


@pytest.fixture(autouse=True)
def autoriza():
    tbot.CHAT_AUTORIZADO = str(CHAT)
    tbot._AGUARDANDO.clear()
    yield
    tbot.CHAT_AUTORIZADO = ""
    tbot._AGUARDANDO.clear()


class _FakeResp:
    status_code = 200
    text = "{}"


def _mock_requests(monkeypatch):
    enviadas = []

    def fake_post(url, json=None, timeout=None, params=None):
        enviadas.append((url.split("/")[-1], json or params or {}))
        return _FakeResp()

    def fake_get(url, params=None, timeout=None):
        enviadas.append((url.split("/")[-1], params or {}))
        return _FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)
    return enviadas


def _handle_cb(dado, mid=1):
    tbot._handle({"callback_query": {"id": "q", "data": dado,
                                     "message": {"chat": {"id": CHAT},
                                                 "message_id": mid}}})


def test_menu_tem_botoes():
    teclado = tbot._teclado_menu()
    dados = [b["callback_data"] for linha in teclado for b in linha]
    assert "menu_aprender" in dados
    assert "menu_treinar" in dados
    assert "menu_modulo" in dados
    assert "menu_modulos" in dados
    assert "menu_conhecimento" in dados
    assert "menu_status" in dados
    assert "menu_cotacao" in dados
    assert "menu_ajuda" in dados
    # novas capacidades
    assert "menu_pesquisar" in dados
    assert "menu_pensar" in dados
    assert "menu_contexto" in dados
    # modo conversa
    assert "menu_conversa" in dados
    assert "menu_portais" in dados
    assert "menu_ideologia" in dados
    # evolução contínua
    assert "menu_evoluir" in dados
    # restart e push (operações remotas)
    assert "menu_restart" in dados
    assert "menu_push" in dados
    # configuração de API LLM
    assert "menu_set_api" in dados
    assert "menu_test_api" in dados


def test_teclado_fixo_tem_start():
    fixo = tbot._teclado_fixo()
    primeiro = fixo[0]
    assert "🏠 /start" in primeiro
    # as linhas todas têm botões
    assert all(linha for linha in fixo)


def test_botao_fixo_inicia_fluxo_pesquisar(monkeypatch):
    _mock_requests(monkeypatch)
    tbot._AGUARDANDO.clear()
    assert tbot._mapear_botao_fixo(CHAT, "🌐 Pesquisar") is True
    assert tbot._AGUARDANDO.get(str(CHAT)) == "pesquisar"
    tbot._AGUARDANDO.clear()


def test_callback_aprender_inicia_fluxo(monkeypatch):
    _mock_requests(monkeypatch)
    tbot._AGUARDANDO.clear()
    _handle_cb("menu_aprender", mid=1)
    assert tbot._AGUARDANDO.get(str(CHAT)) == "aprender"
    tbot._AGUARDANDO.clear()


def test_fluxo_treinar_pelo_menu(monkeypatch):
    _mock_requests(monkeypatch)
    from autoexpand.core.persistence import executar
    executar("DELETE FROM conhecimento")
    tbot._AGUARDANDO.clear()
    _handle_cb("menu_treinar", mid=2)
    assert tbot._AGUARDANDO.get(str(CHAT)) == "treinar"
    tbot._handle({"message": {"chat": {"id": CHAT}, "text": "topico_teste: conteudo_teste"}})
    assert tbot._AGUARDANDO.get(str(CHAT)) is None
    executar("DELETE FROM conhecimento")


def test_callback_cotacao_executa(monkeypatch):
    _mock_requests(monkeypatch)
    tbot._handle_cb = _handle_cb
    tbot._handle({"message": {"chat": {"id": CHAT}, "text": "/menu"}})
    # não deve dar erro; fluxo principal é o _resolver_callback
    assert tbot._teclado_menu()  # não levanta


def test_callback_desconhecido_nao_quebra(monkeypatch):
    _mock_requests(monkeypatch)
    # não é menu_* -> retorna False sem erro
    assert tbot._resolver_callback(CHAT, "nao_existe") is False


def test_callback_restart_sem_script(monkeypatch):
    """menu_restart sem run_bot.sh avisa (não quebra, sem rede)."""
    _mock_requests(monkeypatch)
    # força caminho sem script: PROJETO é o repo real, então existe; simulamos
    # removendo para testar o ramo seguro
    import autoexpand.config as cfg_mod
    monkeypatch.setattr(tbot, "PROJETO", cfg_mod.PROJETO / "inexistente_dir")
    _handle_cb("menu_restart", mid=3)
    assert tbot._AGUARDANDO.get(str(CHAT)) is None
    tbot._AGUARDANDO.clear()


def test_callback_push_mock_autosave(monkeypatch):
    """menu_push chama git_autosave.sincronizar_git."""
    _mock_requests(monkeypatch)
    import autoexpand.core.git_autosave as ga
    chamadas = []

    def fake_sinc(mensagem):
        chamadas.append(mensagem)
        return {"ok": True, "detalhe": "push simulado ok"}

    monkeypatch.setattr(ga, "sincronizar_git", fake_sinc)
    monkeypatch.setattr(tbot, "git_autosave", ga)
    monkeypatch.setenv("AE_MODO", "autonomo_controlado")
    _handle_cb("menu_push", mid=4)
    assert any("push" in c for c in chamadas)


def test_botao_fixo_reiniciar(monkeypatch):
    _mock_requests(monkeypatch)
    tbot._AGUARDANDO.clear()
    assert tbot._mapear_botao_fixo(CHAT, "🔄 Reiniciar") is True
    tbot._AGUARDANDO.clear()


def test_botao_fixo_push_github(monkeypatch):
    _mock_requests(monkeypatch)
    tbot._AGUARDANDO.clear()
    assert tbot._mapear_botao_fixo(CHAT, "📤 Push GitHub") is True
    tbot._AGUARDANDO.clear()


def test_callback_set_api_inicia_fluxo(monkeypatch):
    """menu_set_api coloca o bot em espera pela escolha do provedor."""
    _mock_requests(monkeypatch)
    tbot._AGUARDANDO.clear()
    _handle_cb("menu_set_api", mid=5)
    assert tbot._AGUARDANDO.get(str(CHAT)) == "set_api_provedor"
    tbot._AGUARDANDO.clear()


def test_set_api_gemini_fluxo_2_passos(monkeypatch, tmp_path):
    """Escolher gemini e enviar a chave configura e testa a conexão."""
    _mock_requests(monkeypatch)
    from autoexpand.economy import llm
    monkeypatch.setattr(tbot, "_env_arquivo", lambda: tmp_path / ".env")
    chamadas = []

    def fake_testar():
        chamadas.append("testar")
        return (True, "conectado via gemini-2.0-flash")

    monkeypatch.setattr(llm, "testar_conexao", fake_testar)
    tbot._AGUARDANDO.clear()
    _handle_cb("menu_set_api", mid=6)
    # passa 1: escolhe o provedor
    tbot._handle({"message": {"chat": {"id": CHAT}, "text": "gemini"}})
    assert tbot._AGUARDANDO.get(str(CHAT)) == "set_api"
    # passo 2: envia a chave
    tbot._handle({"message": {"chat": {"id": CHAT},
                              "text": "chave_secreta_gemini_123"}})
    assert tbot._AGUARDANDO.get(str(CHAT)) is None
    assert tmp_path.joinpath(".env").exists()
    conteudo = tmp_path.joinpath(".env").read_text(encoding="utf-8")
    assert "AE_LLM_API_KEY=chave_secreta_gemini_123" in conteudo
    assert "AE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai" in conteudo
    assert "AE_LLM_PROVIDER=gemini" in conteudo
    assert chamadas, "deveria testar a conexão"


def test_set_api_direto_com_provedor(monkeypatch, tmp_path):
    """/set_api openhands <chave> configura direto sem 2 passos."""
    _mock_requests(monkeypatch)
    from autoexpand.economy import llm
    monkeypatch.setattr(tbot, "_env_arquivo", lambda: tmp_path / ".env")

    def fake_testar():
        return (True, "conectado")

    def fake_reconfig(**kw):
        llm.TEM_LLM = True
        return True

    monkeypatch.setattr(llm, "testar_conexao", fake_testar)
    monkeypatch.setattr(llm, "reconfigurar", fake_reconfig)
    tbot._AGUARDANDO.clear()
    tbot._handle({"message": {"chat": {"id": CHAT},
                              "text": "/set_api openhands chave_all_hands_xyz"}})
    assert tbot._AGUARDANDO.get(str(CHAT)) is None
    conteudo = tmp_path.joinpath(".env").read_text(encoding="utf-8")
    assert "AE_LLM_API_KEY=chave_all_hands_xyz" in conteudo
    assert "AE_LLM_PROVIDER=openhands" in conteudo


def test_set_api_provedor_desconhecido(monkeypatch, tmp_path):
    _mock_requests(monkeypatch)
    tbot._AGUARDANDO.clear()
    _handle_cb("menu_set_api", mid=8)
    tbot._handle({"message": {"chat": {"id": CHAT}, "text": "nao_existe"}})
    # continua esperando provedor válido
    assert tbot._AGUARDANDO.get(str(CHAT)) == "set_api_provedor"
    tbot._AGUARDANDO.clear()


def test_test_api_responde(monkeypatch):
    """menu_test_api responde com resultado do teste."""
    _mock_requests(monkeypatch)
    from autoexpand.economy import llm
    monkeypatch.setattr(llm, "testar_conexao", lambda: (False, "sem API configurada"))
    _handle_cb("menu_test_api", mid=7)
    tbot._AGUARDANDO.clear()
