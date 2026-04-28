# DocsQA Evaluation Harness Report
**Generated:** 2026-10-02 18:33:22 UTC
**Golden set:** 50 questions (40 answerable, 10 should be refused)
**Environment:** database=`postgresql`, model_provider=`stub`, embedding_model=`stub-embedding@stub-v1.0`

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Refusal acc. | False refusals | Valid citations | Faithfulness | Avg latency | P95 latency |
|---|---|---|---|---|---|---|---|---|---|---|
| vector | 32.5% | 55.0% | 65.0% | 0.449 | 100.0% | 15.0% | 85.0% | 95.9% | 3.5ms | 5.0ms |
| fts | 52.5% | 80.0% | 87.5% | 0.667 | 90.0% | 5.0% | 95.0% | 98.1% | 2.9ms | 4.1ms |
| hybrid | 45.0% | 65.0% | 77.5% | 0.560 | 90.0% | 5.0% | 95.0% | 98.2% | 7.5ms | 10.4ms |

### Hit@3 by question category

| Mode | easy_lookup | multi_topic |
|---|---|---|
| vector | 56.0% | 53.3% |
| fts | 88.0% | 66.7% |
| hybrid | 64.0% | 66.7% |

A hit means a retrieved chunk is from an expected file and section. Faithfulness is a lexical proxy (share of answer words found in the cited chunks); with the stub model, answers are extracted from the context, so it is high by construction. Retrieval hits are scored on what was retrieved, even when the generator then refused.
