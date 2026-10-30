# PROGRESS

## Objetivo atual
Entregar a demonstração do PaperMind: ensaio da entrevista técnica (`docs/interview/LEIA-ME.md`); a avaliação com artigo real continua pendente.

## Concluído
- 001 ambiente-local: 6 serviços no Compose; N1, N2 e N3 validados.
- 002 ingestão de PDF, 003 indexação e recuperação (pgvector), 004 grafo LangGraph (3 decisões), 005 API, 006 interface Streamlit, 007 cache Redis, 008 ferramentas de avaliação e documentação.
- Verificador: regra de texto e regra de cobertura por frase (V2), feedback que lista as frases sem marcador, `VERIFIER_VERSION=3` na chave do cache (ver `docs/decisions.md`).
- Artigo de teste indexado: Wei et al. (2022), `2201.11903v6.pdf`, 43 páginas, 210 chunks (documento `36b69b98-1bdc-43e8-b6e0-fde6dd608c83`).
- Material de entrevista em `docs/interview/`.
- Testes (29/10/2026): 165 unitários passando no contêiner e no host. Os 11 de integração não foram executados nessa data; o último registro de aprovação deles é da fase com 71 unitários.

## Em andamento
- Ensaio da entrevista técnica.

## Decisões
Ver `docs/decisions.md`. Configuração em vigor em 29/10/2026: `PROMPT_VERSION=6`, `VERIFIER_VERSION=3`, `GROUNDING_THRESHOLD=0.60`, `RELEVANCE_THRESHOLD=0.55` (`pipeline_version` `db4bc1a7ee38`).

## Problemas
- Limiares 0.55/0.60 não calibrados.
- Validação de 29/10/2026 ("What limitations of chain-of-thought prompting do the authors identify?"): `insufficient`. A V4b reprovou as 8 frases das 2 tentativas (similaridade 0.476 a 0.589), embora o trecho com as limitações tenha sido recuperado. Os rascunhos rejeitados não são registrados, então não se sabe se eram corretos.
- Latência do modelo em CPU: ~66 s por resposta (contêiner frio); 127,5 s na validação de 29/10/2026 (2 chamadas ao chat, 17 a embeddings).
- `eval/questions.json` e `eval/articles.json` vazios: nenhuma taxa de acerto medida.
- Interface sem registro de teste manual no navegador.
- Sem controle de versão (`.git`). Backup manual: `~/papermind-backup-2026-10-29.tar.gz` (sem `.venv`; verificado).
- As pastas `__pycache__` criadas pelo contêiner pertencem ao root e não podem ser apagadas pelo usuário do host.

## Próximos passos
1. Registrar o artigo de teste em `eval/articles.json` (confirmar a licença) e salvar o PDF em `data/`.
2. Escrever as 20 perguntas em `eval/questions.json`.
3. `docker compose exec app python -m scripts.calibrate_threshold <document_id>` e ajustar o `.env`.
4. `docker compose exec app python -m scripts.run_eval` e pontuar a rubrica.
5. Ensaiar `docs/interview/roteiro-do-apresentador.md` (roteiro da entrevista) e `docs/demo-script.md` (demo do PRD §19).
Último comando validado: `docker compose exec app python -m pytest` (165 passed, 11 deselected) em 29/10/2026.
