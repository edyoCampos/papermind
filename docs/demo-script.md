# Roteiro da demo (≈ 5 a 6 min)

Antes: `docker compose up -d`; `docker compose exec app python -m scripts.check_env` todo "OK"; artigo já indexado e resumo já gerado (em CPU leva minutos e fica guardado); `docker compose exec redis redis-cli FLUSHDB`; fechar apps pesados.

| # | Passo | Resultado esperado |
|---|---|---|
| 1 | Problema e público em 30 s | — |
| 2 | Upload de um PDF curto; status até "Pronto" (ou artigo já indexado) | Recebido → Extraindo texto → Indexando → Pronto |
| 3 | "Gerar resumo" | 5 seções; mostrar uma "Não encontrado", se houver |
| 4 | Pergunta sobre metodologia/resultado *(escolher do `eval/questions.json`)* | Resposta com fonte e página, selo MISS; conferir a página no PDF |
| 5 | "Explicar termo" com um termo do artigo | Blocos "No artigo" e "Explicação simplificada — gerada pelo modelo" |
| 6 | Pergunta sem resposta no artigo | Aviso de insuficiência; "Caminho no grafo": router → researcher → insufficient |
| 7 | Redis: repetir a pergunta do passo 4 | Selo HIT, < 1 s, mesmas citações; `redis-cli --scan --pattern 'papermind:qa:*'`, `TTL`, contadores em `/health`; `docker compose stop redis` + repetir a do passo 6 (selo "cache indisponível"; termina sem LLM só pela interrupção segura); `docker compose start redis` |
| 8 | Grafo em `docs/architecture.md`; `docker compose exec postgres psql -U papermind -d papermind -c 'select count(*) from document_chunks'`; `docker compose run --rm --no-deps app pytest` | Testes passam |
| 9 | Uma limitação conhecida e o próximo passo técnico | Latência em CPU; limiares ainda a calibrar |

As perguntas exatas dos passos 4 a 6 dependem do artigo escolhido: preencha-as aqui depois de criar `eval/questions.json`.
