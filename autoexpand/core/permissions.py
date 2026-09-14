"""Catálogo declarativo de permissões.

Toda permissão é declarada em `TODOS` e descrita em `NOMES`.
Um script NUNCA pode obter uma permissão por auto-declaração:
ela precisa estar no manifesto *e* ser concedida/verificada pelo registro.
"""

TODOS = frozenset({
    "ler_pedidos",
    "escrever_pedidos",
    "ler_db",
    "escrever_db",
    "ler_api",
    "chamar_api",
    "navegador",
    "rede",
    "mensagens",
    "pagamentos",
    "credenciais",
    "sistema",
    "instalar_pacotes",
})

# Ações que SEMPRE exigem aprovação humana, independente do manifesto.
AUTO_APROVADAS = frozenset({
    "ler_pedidos",
    "ler_db",
    "ler_api",
    "rede",          # apenas leitura/handshake — tratada como alcancável sem escrutínio
})

APROVACAO_MINIMA_OBRIGATORIA = frozenset({
    "escrever_pedidos",   # escrita em dados
    "escrever_db",        # escrita em dados
    "mensagens",          # envio de mensagens
    "pagamentos",         # pagamentos
    "credenciais",        # alteração de credenciais
    "instalar_pacotes",   # instalar dependências
    "sistema",            # acesso amplo a sistema
})

CRITICAS = frozenset({"pagamentos", "credenciais", "sistema", "instalar_pacotes"})

NOMES = {
    "ler_pedidos": "Ler pedidos autorizados",
    "escrever_pedidos": "Escrever/criar pedidos",
    "ler_db": "Ler banco de dados",
    "escrever_db": "Escrever no banco de dados",
    "ler_api": "Chamar APIs em modo leitura",
    "chamar_api": "Chamar APIs autorizadas (leitura/escrita)",
    "navegador": "Automação de navegador (Playwright)",
    "rede": "Acesso de rede",
    "mensagens": "Enviar mensagens (Telegram, e-mail, Slack)",
    "pagamentos": "Realizar pagamentos",
    "credenciais": "Alterar/ler credenciais",
    "sistema": "Acesso amplo ao sistema",
    "instalar_pacotes": "Instalar/atualizar pacotes",
}

# Como um manifesto novo é tratado: apenas leitura/neutro vão para rascunho
# diretamente; tudo que envolve efeitos colaterais exige rascunho + aprovação.
def exige_aprovacao_por_padrao(permissao: str) -> bool:
    """Se a permissão não é de leitura/neutra, exige aprovação humana."""
    return permissao not in AUTO_APROVADAS