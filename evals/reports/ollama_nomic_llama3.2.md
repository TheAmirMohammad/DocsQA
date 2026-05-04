# DocsQA Evaluation Harness Report
**Generated:** 2026-10-02 18:41:24 UTC
**Golden set:** 50 questions (40 answerable, 10 should be refused)
**Environment:** database=`postgresql`, model_provider=`ollama`, embedding_model=`nomic-embed-text@ollama-embed-v2`

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Refusal acc. | False refusals | Valid citations | Faithfulness | Avg latency | P95 latency |
|---|---|---|---|---|---|---|---|---|---|---|
| vector | 75.0% | 95.0% | 97.5% | 0.852 | 100.0% | 15.0% | 85.0% | 64.5% | 3118.2ms | 6689.7ms |
| fts | 52.5% | 80.0% | 87.5% | 0.667 | 100.0% | 27.5% | 72.5% | 60.9% | 3194.8ms | 6117.1ms |
| hybrid | 70.0% | 92.5% | 92.5% | 0.800 | 100.0% | 20.0% | 80.0% | 63.9% | 3416.3ms | 7438.8ms |

### Hit@3 by question category

| Mode | easy_lookup | multi_topic |
|---|---|---|
| vector | 96.0% | 93.3% |
| fts | 88.0% | 66.7% |
| hybrid | 92.0% | 93.3% |

A hit means a retrieved chunk is from an expected file and section. Faithfulness is a lexical proxy (share of answer words found in the cited chunks); with the stub model, answers are extracted from the context, so it is high by construction. Retrieval hits are scored on what was retrieved, even when the generator then refused.
