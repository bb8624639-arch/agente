# Configuração dos testes: isola o estado em um diretório temporário
# para NUNCA tocar no banco/estado de produção (state/ do projeto).
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="ae_teste_")
os.environ["AE_STATE_DIR"] = _tmp