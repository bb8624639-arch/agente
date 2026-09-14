# Contrato de integração com o Painel existente

O painel **não** é reconstruído aqui; ele consome esta API (Flask) via `web/api.py`.
Abra com `python3 -m autoexpand.web.api` (porta 8080 default) ou `flask --app`.

## Autenticação
`Authorization: Bearer $AE_API_TOKEN`. Se `AE_API_TOKEN` estiver vazio (dev),
a API fica aberta. Em produção, defina um token e sirva atrás de HTTPS/reverse-proxy.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/modulos` | lista módulos + domínios autorizados |
| GET | `/api/modulos/<nome>/versoes` | histórico de versões do módulo |
| GET | `/api/aprovacoes/pendentes` | fila de aprovações humanas |
| POST | `/api/aprovacoes/<id>/decidir` | `{"aprovado": true/false, "por": "nome"}` |
| POST | `/api/emergencia` | `{"acionar": true/false}` — botão de emergência |
| GET | `/api/consumo` | contadores (tarefa/dia/mês) e tetos |
| GET | `/api/limites` | configuração de limites econômicos |
| POST | `/api/sites/autorizar` | `{"dominio": "exemplo.com"}` — allowlist |
| POST | `/api/sites/remover` | `{"dominio": "exemplo.com"}` |
| GET | `/api/diario` | últimas entradas do diário (logs) |
| GET | `/api/execucoes` | últimas execuções |

## Exemplos

```bash
# listar módulos
curl -s localhost:8080/api/modulos

# aprovar ação sensível (pedido gerado pelo executor)
curl -s -X POST localhost:8080/api/aprovacoes/<id>/decidir \
  -H 'Content-Type: application/json' -d '{"aprovado": true, "por": "Ana"}'

# autorizar domínio p/ leitura
curl -s -X POST localhost:8080/api/sites/autorizar \
  -H 'Content-Type: application/json' -d '{"dominio": "exemplo.com.br"}'

# botão de emergência
curl -s -X POST localhost:8080/api/emergencia -d '{"acionar": true}'
```

## Contrato do relatório (formato 11 itens)
Preenchido pelo executor (`orchestrator/executor.py`) e retornado via CLI ou Telegram.

## Observações de segurança
- Credenciais nunca transitam nesta API; apenas referências.
- Exclusões/modificações de domínios e emergência exigem autenticação com papel humano
  (a API só regista quem decidiu; reforço de papel fica para o painel).