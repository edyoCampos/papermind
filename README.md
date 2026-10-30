# PaperMind

Assistente multiagente local para ler artigos científicos em PDF (RAG + LangGraph + pgvector + Redis + Ollama). Tudo roda em Docker Compose; o host só precisa de Docker.

## Pré-requisitos
- Docker Engine e Compose v2.20+.
- Contexto Docker nativo: `docker context use default` (o Docker Desktop parado causa `failed to connect to the docker API`).
- Primeira execução: internet e ~4 a 6 GB de download (imagens, dependências e modelos de ~2,3 GB). Depois funciona offline.

## Subir
```bash
cp .env.example .env        # se mudar POSTGRES_PASSWORD, mude DATABASE_URL junto
docker compose up -d --build
docker compose ps
docker compose exec app python -m scripts.check_env
```
Interface: http://127.0.0.1:8501 · API: http://127.0.0.1:8000/health · Docs: http://127.0.0.1:8000/docs

## Testes
```bash
docker compose run --rm --no-deps app pytest            # unitários
docker compose run --rm app pytest -m integration       # contra os serviços reais
```

## Operação
- Parar mantendo dados: `docker compose down`. Reset total (apaga modelos): `docker compose down -v`.
- Só o banco: `docker compose down` e `docker volume rm papermind_pg_data`.
- Adicionar dependência: `docker run --rm -v "$PWD":/work -w /work ghcr.io/astral-sh/uv:0.11.21 add <pacote>` e `docker compose build app frontend`.

## Troubleshooting
| Sintoma | Solução |
|---|---|
| `failed to connect to the docker API ... desktop.sock` | `docker context use default` |
| Porta 8000/8501 ocupada | mude `APP_PORT`/`FRONTEND_PORT` no `.env` |
| `ollama-init` com código ≠ 0 | sem internet na 1ª execução; reconecte e `docker compose up -d` |
| Ollama `exited (137)` (falta de memória) | feche apps pesados ou use `CHAT_MODEL=qwen2.5:1.5b` |
| `dimensão real ≠ EMBEDDING_DIM` | ajuste `EMBEDDING_DIM` ao modelo |
| Falha de autenticação no Postgres após trocar senha | `docker volume rm papermind_pg_data` |
| Redis fora | o app segue sem cache; `check_env` mostra FALHA só no Redis |

## Usando a interface
Abra http://127.0.0.1:8501, envie o PDF e aguarde "Pronto". "Gerar resumo" produz as 5 seções (em CPU pode levar minutos; fica guardado). No chat, escolha o modo: Automático, Pergunta sobre o artigo ou Explicar termo. O expander "Caminho no grafo" mostra quais agentes atuaram.

## Cache Redis (roteiro de 60 s)
1. Faça uma pergunta: selo MISS. Repita: selo HIT, mesmas fontes.
2. `docker compose exec redis redis-cli --scan --pattern 'papermind:qa:*'` e `TTL <chave>`.
3. Contadores em http://127.0.0.1:8000/health.
4. `docker compose stop redis`: pergunta nova roda o fluxo completo e mostra "cache indisponível"; `docker compose start redis`.
Limpar: `docker compose exec redis redis-cli FLUSHDB`. Desligar: `CACHE_ENABLED=false` no `.env`.

## Avaliação e demo
Veja `docs/demo-script.md` (roteiro), `docs/decisions.md` (decisões e limiares) e `PROGRESS.md` (próximos passos). Avaliação: `docker compose exec app python -m scripts.run_eval` (precisa de `eval/articles.json` e `eval/questions.json`).
