"""Testes do classificador e planejador (regras, sem IA)."""
from autoexpand.orchestrator.classifier import classificar, ambiguidade
from autoexpand.orchestrator.planner import planejar


def test_classifica_leitura():
    cl = classificar("consulte o preço do produto na página autorizada")
    assert cl.categoria in ("pesquisa", "navegador")


def test_classifica_mensagem():
    cl = classificar("envie uma mensagem para o cliente pelo whatsapp")
    assert cl.categoria == "mensagens"
    assert cl.acao == "enviar_mensagem"


def test_classifica_erro():
    cl = classificar("está dando erro no pedido 123")
    assert cl.categoria == "erro"


def test_classifica_desconhecida():
    cl = classificar("aloha festa")
    assert cl.categoria == "desconhecida"


def test_ambiguidade_familia_leitura_nao_dispara():
    assert not ambiguidade("consulte o preço do produto na página autorizada")


def test_ambiguidade_real_dispara():
    assert ambiguidade("envie uma mensagem no whatsapp e registre pagamento pix")


def test_plano_leitura_sem_aprovacao():
    cl = classificar("consulte o preço do produto na página autorizada")
    plano = planejar("consulte o preço do produto na página autorizada", cl)
    assert plano["status"] == "plano"
    assert plano["aprovacao_necessaria"] is False
    assert "browser/reader" in plano["ferramentas"]


def test_plano_mensagem_exige_aprovacao():
    cl = classificar("envie uma mensagem para o cliente pelo whatsapp")
    plano = planejar("envie uma mensagem para o cliente pelo whatsapp", cl)
    assert plano["aprovacao_necessaria"] is True


def test_plano_financeiro_bloqueado():
    cl = classificar("fazer um pix de 50 reais")
    plano = planejar("fazer um pix", cl)
    assert plano["aprovacao_necessaria"] is True


def test_plano_desconhecida_pede_desambiguacao():
    cl = classificar("aloha festa")
    plano = planejar("aloha festa", cl)
    assert plano["status"] == "precisa_desambiguacao"