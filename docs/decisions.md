# Decisões

## Ambiente (feature 001)
- Tags fixas: `pgvector/pgvector:0.8.7-pg16`, `ollama/ollama:0.40.12`, `redis:7.4-alpine`, `ghcr.io/astral-sh/uv:0.11.21`, `python:3.12-slim-bookworm`.
- Arquivo compose mantido como `compose.yaml`. Dockerfile e compose provisórios do autor estão em `_reversa_forward/001-ambiente-local/originais/`.
- `frontend/app.py` sombreia o pacote `app`; por isso o frontend lê `API_URL` do ambiente e não importa `app.*`.
- Docker Engine nativo (`docker context use default`), tudo em Compose, só as portas 8000 e 8501 em 127.0.0.1.

## Ingestão e indexação (features 002, 003)
- Chunking por página (citação exata); página física como número citado; mínimo de 200 caracteres para "sem texto".
- SQL explícito com psycopg 3 + pgvector (em vez de `langchain-postgres`); busca exata sem índice ANN; limiar único sobre a similaridade máxima; prefixos `search_document:`/`search_query:`.

## Grafo (feature 004)
- Roteador por regra + modo explícito (sem LLM); verificador determinístico V1–V4; explicação sem suporte só informa a limitação; citações montadas dos chunks; resumo por 5 consultas fixas; um único modelo local.

## API e interface (features 005, 006)
- `BackgroundTasks` + polling de status; validação síncrona antes do 202; `/health` sempre 200.
- Reiniciar a API no meio da indexação deixa o documento em `indexing`; basta reenviar o PDF.
- Interface consome só a API; modo "Automático" por padrão; expander "Caminho no grafo".

## Cache (feature 007)
- Redis só como cache de respostas; `pipeline_version` na chave; envoltório fora do grafo; contadores no Redis; Redis falso manual nos testes.

## Limiares (feature 008) — NÃO CALIBRADOS
| Parâmetro | Valor atual | Situação |
|---|---|---|
| `RELEVANCE_THRESHOLD` | 0.55 | valor inicial; calibrar com `scripts.calibrate_threshold` |
| `GROUNDING_THRESHOLD` | **0.60** (V4b reativada) | ficou em 0 de 01:51 a ~02:00 UTC de 2026-10-29; ver "V4b desligada" e "V4b reativada" abaixo |

Falta o artigo público de avaliação, as 20 perguntas (`eval/questions.json`, com ≥6 `calibration`), a calibração e a rubrica manual. Registre aqui o valor final e a tabela que o justificou.

## V4b desligada (GROUNDING_THRESHOLD=0) — 2026-10-29
Procedimento previsto em `_reversa_sdd/sdd/grafo-multiagente.md` §13: "Se o verificador reprovar respostas boas em excesso na calibração, desligar só V4b (`GROUNDING_THRESHOLD=0`) e registrar em `docs/decisions.md`; V1 a V4a continuam."

**Problema observado.** Na pergunta "What limitations of chain-of-thought prompting do the authors identify?", com a recuperação já trazendo o trecho das limitações (chunk 82), o leitor produziu 5 frases, todas com marcador válido, e a V4b reprovou todas: similaridade frase × trecho entre 0.470 e 0.500, abaixo de 0.60. A reformulação terminou em `SEM_EVIDENCIA`. O texto rejeitado não foi registrado, então não se sabe se estava correto.

**Calibração** (mesmo `Embedder`, mesma limpeza de marcadores e mesma função `_cos()` da V4b; 4 afirmações sabidamente corretas, em português, contra o trecho em inglês que as sustenta, página 9):

| Afirmação correta | Similaridade com o trecho correto | Limiar 0.60 |
|---|---:|---|
| 1 — não se sabe se a rede "raciocina" (chunk 81) | 0.633 | passa |
| 2 — custo de anotação para ajuste fino (chunk 82) | 0.551 | reprova |
| 3 — sem garantia de caminho de raciocínio correto (chunk 82) | 0.485 | reprova |
| 4 — só em escala grande, caro para servir (chunk 82) | 0.540 | reprova |

**3 de 4 afirmações corretas ficariam abaixo do limiar.** Na afirmação 1, o trecho citado por engano (página 4) teve 0.578, contra 0.633 do correto: a métrica separa pouco o trecho certo do errado.

**Limitações da evidência.** Quatro exemplos, todos em português contra trechos em inglês, não calibram o verificador de forma geral nem permitem escolher outro limiar. Por isso a V4b foi desligada, e não ajustada para outro número.

**Similaridade não é comprovação.** A V4b mede proximidade de assunto entre embeddings, não se o trecho afirma o que a frase diz. Mesmo ligada, nunca comprovou suporte factual.

**O que continua ativo.** V1 (`SEM_EVIDENCIA`), V2 (ao menos um marcador), V3 (marcador aponta para evidência existente) e V4a (números da frase presentes no trecho citado). Nenhuma delas verifica suporte semântico.

**Trade-off.** Menos respostas corretas rejeitadas, em troca de menos proteção contra citações irrelevantes ou trechos errados. A conferência final é do usuário, que vê página e trecho de cada citação.

**Efeitos colaterais.** Com a V4b desligada, `check()` não calcula a similaridade da frase, e os campos `frase_vs_trecho_*` do log saem `-`. O limiar entra na chave de cache, então o `pipeline_version` muda e as respostas antigas deixam de ser lidas sem precisar apagar nada do Redis.

**Reversão.** No `.env`, voltar `GROUNDING_THRESHOLD=0` para `GROUNDING_THRESHOLD=0.60` e recriar só o serviço `app`: `DOCKER_CONTEXT=default docker compose up -d --no-deps app` (o `.env` só é lido quando o contêiner é criado).

## V4b reativada e exemplo removido do prompt (PROMPT_VERSION=4) — 2026-10-29
**Fato novo.** Com a V4b desligada, a mesma pergunta foi aprovada (`answered`) com esta resposta: "O método melhorou os resultados [1]. O método melhorou os resultados [3]. O método melhorou os resultados [4]. O método melhorou os resultados [5]. O método melhorou os resultados [6]." É a frase de exemplo do próprio prompt, copiada cinco vezes, com citações reais (páginas 4, 8 e 9) que não a sustentam. V2, V3 e V4a a aprovaram, porque checam formato, existência da citação e números.

**Hipótese (não comprovada).** A resposta que a V4b reprovou na execução anterior tinha o mesmo tamanho (184 caracteres), as mesmas 5 frases marcadas e os mesmos trechos citados. Com o mesmo prompt, contexto e temperatura 0, é provável que fosse a mesma cópia: a V4b teria reprovado um erro real, não uma resposta correta. O texto daquela execução não foi guardado.

**Causa provável da cópia.** O prompt da versão 3 trazia a frase "O método melhorou os resultados [n]" duas vezes (regra de exemplo e lembrete final). Uma chamada direta sem exemplos produziu uma resposta real com as 4 limitações, mas aquela chamada mudou mais de uma coisa ao mesmo tempo; a relação não está isolada.

**O que mudou.** Prompt (`app/agents/prompts.py`): sai a frase de exemplo; entra a regra "Não copie frases destas instruções para a resposta."; o lembrete final passa a pedir resposta direta e citação em cada afirmação, sem exemplo e sem repetir `SEM_EVIDENCIA` (a regra de recusa fica uma vez, no cabeçalho). `.env`: `PROMPT_VERSION` 3 → 4 (o texto do prompt não entra na chave de cache; o número sim) e `GROUNDING_THRESHOLD` 0 → 0.60.

**Por que a V4b volta.** O RF-08 da spec do grafo (Must) define V1 a V4 no fluxo normal; o rollback do §13 é exceção para quando a V4b "reprova respostas boas em excesso". A calibração mostra que ela pode reprovar afirmações corretas (3 de 4), mas a reprovação que motivou o rollback provavelmente era de uma cópia, e sem a V4b uma não-resposta foi aprovada. A V4b continua sem comprovar suporte factual; ela é uma barreira imprecisa contra frases sem relação com o trecho.

**Pendente.** Avaliar a V4b com o prompt corrigido: se respostas corretas forem reprovadas em excesso, aí sim o §13 se aplica, agora com evidência. Quatro exemplos de calibração continuam insuficientes para escolher outro limiar.

## Resposta sem afirmação textual passa a reprovar (PROMPT_VERSION=5) — 2026-10-29
**Fato.** Com `PROMPT_VERSION=4`, a pergunta sobre limitações foi aprovada (`answered`) com a resposta literal `[3]`. Depois de remover o marcador, a frase fica vazia: V2 viu um marcador, V3 viu que `[3]` existe, V4a não achou números e a V4b pula frases vazias. Nenhuma checagem exigia texto.

**Extensão da spec.** O §6.6 de `_reversa_sdd/sdd/grafo-multiagente.md` exige "ao menos 1 marcador", mas não diz nada sobre conteúdo. Acrescentado ao verificador, na família V2: depois de remover os marcadores, a parte factual precisa ter ao menos uma letra; senão reprova com "V2: a resposta não tem nenhuma afirmação em texto, só marcadores ou pontuação." O fluxo existente se mantém (1 reformulação com esse feedback, depois `insufficient`). A mensagem "faltou o bloco 'NO ARTIGO:'" passou a valer só no modo explicação; uma resposta factual vazia continua reprovada, agora pela regra nova.

**Limite.** A regra só garante que há texto. Não verifica se o texto responde à pergunta nem se a citação o sustenta.

**Cache.** O código do verificador não entra no `pipeline_version`; o único controle de versão existente é `PROMPT_VERSION`, que subiu de 4 para 5 e passa a versionar o par prompt + verificação. (Superado: ver "VERIFIER_VERSION na chave do cache".)

## Lembrete pede resposta em prosa (PROMPT_VERSION=6) — 2026-10-29
**Mudança.** Só o lembrete final do prompt (usado pelo leitor e pelo resumo) passou de "responda diretamente à pergunta usando apenas as evidências. Termine cada afirmação com o marcador da evidência que a sustenta." para "responda diretamente à pergunta em prosa, com frases completas, usando somente as evidências fornecidas. Coloque o marcador correspondente logo após cada afirmação sustentada." Regras, evidências, legenda e verificador não mudaram. `PROMPT_VERSION` 5 → 6.

**Hipótese (não comprovada).** O lembrete anterior, último texto antes de "Resposta:", podia ser lido como "responda com o marcador", e o modelo devolvia só `[3]` (2 de 2 vezes na produção e 1 de 1 em chamada direta). Numa única chamada direta com o lembrete novo, o modelo escreveu três limitações reais do artigo, mas com os marcadores no início e citando trechos que não sustentavam duas delas.

**Risco conhecido.** O lembrete novo pode trocar uma recusa segura por uma resposta com texto e citações inadequadas. A proteção continua sendo o verificador (V2 a V4b), que não comprova que a citação sustenta a afirmação.

## Cobertura de citações por frase (V2) — 2026-10-29
**Fato.** Com `PROMPT_VERSION=6`, a resposta sobre limitações foi aprovada com 4 frases e marcadores só na primeira (genérica); as três frases com as limitações não tinham citação. A V4b só avalia frases com marcador, então nada checou as outras três.

**Regra nova (família V2, extensão do §6.6 da spec do grafo).** Depois das regras V2 existentes, toda parte da resposta que tiver letras após remover os marcadores precisa ter ao menos um `[n]`; senão reprova com "V2: N frase(s) com afirmação sem marcador; …". Partes só com marcador não contam como afirmação. A regra garante **cobertura**, não **suporte**: não verifica se o trecho citado sustenta a frase.

**Limite do separador (conservador).** As frases são divididas por `.`, `!` ou `?` seguidos de espaço (o mesmo separador da V3 e da V4). Decimais como `92.5` não quebram. Abreviações quebram: em "Wei et al. mostraram… [1]", a parte "Wei et al." fica sem marcador e a resposta é reprovada (falso positivo, do lado seguro). Marcador depois do ponto ("A. [1] B") vai para a frase seguinte. Os dois casos têm teste.

**Lacuna de versionamento.** O código do verificador não entra no `pipeline_version` (RF-02 da spec do cache). Mudar o verificador não invalida respostas aprovadas pela regra antiga; até o TTL vencer, elas continuam sendo servidas. Opções: subir `PROMPT_VERSION` (mecanismo existente, conceitualmente impreciso) ou incluir uma versão do verificador na chave (mudança de código e da spec). Resolvida na seção seguinte.

## VERIFIER_VERSION na chave do cache — 2026-10-29
**Mudança.** `Settings.verifier_version` (padrão `"2"`, variável `VERIFIER_VERSION`) passou a entrar no `pipeline_version`, junto com modelos, chunking, limiares e `PROMPT_VERSION` (`app/services/cache.py`; RF-02 da spec do cache, versão 1.3; seção 9 da spec do ambiente, versão 1.3). Versão 1 = regras anteriores às de texto e cobertura; versão 2 = regras atuais.

**Razão.** Impedir que respostas aprovadas por regras antigas do verificador sejam servidas do cache depois que as regras mudam, sem apagar chaves nem mexer em TTL: com outra versão, a chave muda, e as respostas antigas ficam no Redis até expirar, mas não são mais lidas.

**Efeito medido.** `pipeline_version` passou de `5d4db9c6fb1a` para `8aaf03e91033` (com `VERIFIER_VERSION=1` seria `be5c6896a31c`). As 6 chaves existentes continuaram no Redis, idênticas; contadores inalterados.

**Testes.** `pytest tests/services/test_cache.py tests/test_config.py -v`: 17 passaram (5 novos: mesma configuração gera a mesma versão; mudar só `VERIFIER_VERSION` muda a versão e preserva o resto da chave; `PROMPT_VERSION` continua mudando a versão; padrão `"2"` com sobrescrita pelo ambiente; resposta antiga fica guardada mas não é lida). Suíte unitária: 160 passaram, 11 de integração excluídos. Uma primeira execução falhou em `test_env_example_cobre_settings` porque o `.env.example` dentro do contêiner era a cópia do build anterior (o arquivo não é montado do host); resolvido reconstruindo a imagem (`docker compose build app`) e recriando só o `app`.

**Limitações.** A versão é manual: quem mudar as regras do verificador precisa subir `VERIFIER_VERSION` no `config.py` (padrão), ou respostas antigas voltam a ser reaproveitadas. Como é variável de ambiente, um valor fixado no `.env` sobrepõe o padrão do código e pode ficar defasado. Arquivos fora das pastas montadas (como `.env.example` e `pyproject.toml`) só chegam ao contêiner com um novo build da imagem.

## Feedback acionável da cobertura — 2026-10-29
**Fato.** Na validação com `pipeline_version=8aaf03e91033`, a regra de cobertura reprovou as duas tentativas (1 de 4 e 1 de 3 frases com marcador). O feedback dizia só a quantidade ("N frase(s) com afirmação sem marcador"); como o Reader não vê a própria resposta anterior, a reformulação repetiu o padrão.

**Mudança.** Só a mensagem da regra mudou (`app/agents/verifier.py`). Agora ela lista o início, até 60 caracteres, de cada frase descoberta e pede que a resposta seja reescrita em frases completas, com cada afirmação factual terminando no marcador da evidência que realmente a sustenta ("um marcador que não corresponde a essa evidência não basta"). A regra de cobertura, os demais códigos e a decisão de aprovar ou reprovar não mudaram. Os fragmentos vão só para o feedback do Reader; o log do verificador continua registrando apenas códigos e contagens.

**Testes.** 5 novos (frases descobertas listadas, frases com marcador fora da lista, limite de 60 caracteres, instrução de evidência que sustenta, ausência de texto no log) e o auxiliar de 7 asserções existentes atualizado para a mensagem nova, com igualdade exata. Suíte unitária: 165 passaram, 11 de integração excluídos.

**Limitação.** Um feedback mais específico pode melhorar o formato (cobertura), mas não prova que as citações sustentam as afirmações: o modelo pode marcar todas as frases citando os trechos errados. Os critérios de aprovação não mudaram, então `VERIFIER_VERSION` continua em 2; respostas no cache dessa versão foram geradas com o feedback anterior (só afeta a 2ª tentativa). (Revisto: ver "VERIFIER_VERSION 2 → 3".)

## VERIFIER_VERSION 2 → 3 — 2026-10-29
**Revisão da decisão anterior.** A seção acima manteve a versão 2 porque os critérios de aprovação não mudaram. Mas o `pipeline_version` identifica o que gerou a resposta guardada, não só o critério: a mensagem nova entra no prompt da 2ª tentativa do Reader (`prompts.py` repassa a mensagem V2 sem alteração), então a mesma pergunta pode ter outro resultado, e `insufficient` também vai para o cache. Com a versão 2, uma resposta gerada com o feedback antigo seria servida como se fosse do pipeline atual.

**Mudança.** Padrão de `Settings.verifier_version` `"2"` → `"3"` (`app/core/config.py`), `.env.example` e seção 9 da spec do ambiente (versão 1.4). Versão 3 = regras da versão 2 + feedback que lista as frases sem marcador. `PROMPT_VERSION=6`, limiares, prompt-base, recuperação, grafo e regras de aprovação não mudaram. O `.env` não define `VERIFIER_VERSION`, então vale o padrão do código; o `--reload` do uvicorn aplicou a mudança sem rebuild.

**Efeito medido.** `pipeline_version` `8aaf03e91033` → `db4bc1a7ee38`. O Redis já estava vazio antes da mudança (sem persistência em disco, e os contêineres foram reiniciados em 2026-10-29 14:23 UTC); nada foi apagado por esta mudança.

**Testes.** Em `tests/services/test_cache.py`, duas expectativas fixavam o padrão antigo: o padrão esperado passou de `"2"` para `"3"`, e o teste "mudar só `VERIFIER_VERSION`" passou a comparar com `"99"` (comparava com `"3"`, que agora é o padrão, e deixaria de testar a mudança). Cache e configuração: 17 passaram; suíte unitária: 165 passaram, 11 de integração excluídos (no contêiner e no host).

**Limitação.** A cópia do `.env.example` dentro da imagem continua com `2` até o próximo build (o arquivo não é montado). Não afeta a execução nem os testes, que só conferem as chaves.

## Medições
- qwen2.5:3b em CPU, contêiner frio: pergunta factual respondida em ~66 s (inclui carga do modelo); pergunta sem suporte barrada em ~5 s. Uma pergunta fora do artigo teve similaridade 0.566, passou do limiar 0.55 e foi barrada pelo próprio modelo (SEM_EVIDENCIA, V1).
- Memória em repouso dos 5 contêineres: ~0,65 GiB (a medir sob carga).
