# Arquitetura do grafo

```
START → router ─┬─(summary)──────────────────────────────→ summarizer → END
                └─(factual|explanation)→ researcher → evidence_gate
evidence_gate ─┬─(relevant=False)→ insufficient → END      (sem chamar o LLM)
               └─(relevant=True) → reader → verifier → verification_gate
verification_gate ─┬─(passed)──────────────→ finalize → END
                   ├─(failed, attempts=0)──→ reader   (1 reformulação)
                   └─(failed, attempts=1 ou V1)→ insufficient → END
```
- Estado: `app/graph/state.py` (`PaperState`); montagem: `app/graph/build.py`; nós: `app/agents/`.
- Três decisões do orquestrador: roteamento por intenção, interrupção segura, verificação com no máximo 1 reformulação.
- Verificador determinístico: V1 autodeclaração (`SEM_EVIDENCIA`); V2 texto e marcadores (no modo explicação, bloco "NO ARTIGO:" presente; ao menos uma letra fora dos marcadores; ao menos um `[n]`; um marcador em cada frase com afirmação); V3 marcador válido; V4a números; V4b aderência (cosseno ≥ `GROUNDING_THRESHOLD`). Nenhuma checagem comprova que o trecho citado sustenta a frase.
- Citações vêm dos chunks recuperados (página, trecho), nunca do texto gerado.

## Componentes
| Serviço | Papel |
|---|---|
| `frontend` (Streamlit) | Interface; fala só com a API por httpx |
| `app` (FastAPI) | Rotas, ingestão, grafo LangGraph, cache |
| `postgres` (pgvector) | Documentos, chunks, vetores, resumo |
| `redis` | Cache de respostas (efêmero, TTL) |
| `ollama` | Chat (qwen2.5:3b) e embeddings (nomic-embed-text), só CPU |

Fluxo: PDF → `app/ingestion` (valida, extrai por página, chunks) → `app/services/indexing` (embeddings + gravação transacional) → pergunta → `qa.answer_cached` (Redis) → grafo.

## Responsabilidade de cada nó
| Nó | LLM | Responsabilidade |
|---|---|---|
| router | não | Classifica a intenção (resumo, factual, explicação) |
| researcher | não | Recupera evidências e aplica o limiar de relevância |
| reader | sim | Redige a resposta só com as evidências numeradas |
| verifier | não | Confronta a resposta com os trechos (V1..V4) |
| finalize | não | Monta as citações a partir dos chunks |
| insufficient | não | Mensagem fixa de insuficiência |
| summarizer | sim | Resumo em 5 seções por consultas fixas |
