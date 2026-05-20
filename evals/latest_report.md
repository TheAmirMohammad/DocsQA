# DocsQA Evaluation Harness Report
**Generated:** 2026-10-03 07:50:30 UTC
**Golden set:** 60 questions (48 answerable, 12 should be refused)
**Environment:** database=`sqlite`, model_provider=`stub`, embedding_model=`stub-embedding@stub-v1.0`

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Refusal acc. | False refusals | Valid citations | Lex. Faith. | LLM Faith. | Avg latency | P95 latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vector | 31.2% | 50.0% | 60.4% | 0.417 | 100.0% | 16.7% | 83.3% | 93.3% | 80.2% | 4.2ms | 4.6ms |
| fts | 60.4% | 83.3% | 91.7% | 0.724 | 91.7% | 4.2% | 95.8% | 94.4% | 86.6% | 2.7ms | 3.1ms |
| hybrid | 47.9% | 66.7% | 77.1% | 0.593 | 100.0% | 8.3% | 91.7% | 96.3% | 90.1% | 7.7ms | 16.3ms |
| hybrid_weighted | 50.0% | 66.7% | 72.9% | 0.590 | 100.0% | 8.3% | 91.7% | 96.7% | 89.6% | 7.2ms | 7.8ms |
| hybrid_reranked | 58.3% | 83.3% | 85.4% | 0.702 | 91.7% | 6.2% | 93.8% | 96.7% | 86.0% | 7.3ms | 7.7ms |

### Hit@3 by question category

| Mode | easy_lookup | multi_topic |
|---|---|---|
| vector | 48.5% | 53.3% |
| fts | 78.8% | 93.3% |
| hybrid | 63.6% | 73.3% |
| hybrid_weighted | 63.6% | 73.3% |
| hybrid_reranked | 84.9% | 80.0% |

A hit means a retrieved chunk is from an expected file and section. Faithfulness is a lexical proxy (share of answer words found in the cited chunks); with the stub model, answers are extracted from the context, so it is high by construction. Retrieval hits are scored on what was retrieved, even when the generator then refused.
