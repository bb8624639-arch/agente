# Configuração dos testes: isola o estado em um diretório temporário
# para NUNCA tocar no banco/estado de produção (state/ do projeto).
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="ae_teste_")
os.environ["AE_STATE_DIR"] = _tmp
# Força modo teste nos testes: mesmo que o .env defina AE_MODO=autonomo_controlado,
# a suíte nunca toca rede/ações reais (bot.py carrega .env com setdefault).
os.environ["AE_MODO"] = "teste"