# ADR-0005: Model Adapter Abstraction with Deterministic Offline Stub

## Status
Accepted

## Context
A major failure mode of AI engineering projects is coupling business logic and evaluation suites directly to a paid commercial API (e.g., OpenAI or Anthropic). This creates:
1. Flaky CI tests due to rate limits, network outages, or upstream model latency.
2. Recurring API expenses during continuous integration runs.
3. Inability to test locally in offline environments or on machines without API keys.
4. Non-deterministic evaluation runs where subtle model updates invalidate baseline comparisons.

## Decision Drivers
- **Offline testability:** Unit tests, integration tests, and the evaluation harness must run deterministically in CI with zero external API dependencies and zero costs.
- **Provider neutrality:** The application must easily switch between hosted commercial LLMs (OpenAI, Gemini, Anthropic), local open models (Ollama), and test stubs without changing application code.
- **Strict typing & contracts:** All adapters must satisfy an async Python abstract interface (`BaseModelAdapter`).

## Considered Options
1. **Model Adapter Abstraction with Deterministic Stub (Selected):**
   - Provide an abstract base class `BaseModelAdapter` with `embed(texts)` and `generate(prompt, context)`.
   - Implement three adapters:
     - `StubModelAdapter`: Generates reproducible, normalized 384-dimensional vector embeddings via cryptographic hash projections, and produces deterministic structured answers with citations based on matching context.
     - `OpenAIModelAdapter`: Standard HTTP interface for OpenAI-compatible APIs (OpenAI, Azure, Groq, Together).
     - `OllamaModelAdapter`: Local inference for privacy and offline developer workstations running `llama3.2` or `nomic-embed-text`.
   - *Pros:* Zero CI external calls; 100% reproducible benchmark scores; immediate local testability.
   - *Cons:* Requires maintaining the adapter interface and stub logic.
2. **Direct LangChain / LlamaIndex integration:**
   - *Pros:* Many pre-built connectors.
   - *Cons:* Heavy dependencies, frequent breaking changes, black-box abstraction leaks, difficult to mock cleanly.
3. **Mocking via HTTP interception (e.g. `responses` or `vcrpy`):**
   - *Pros:* Captures real API responses.
   - *Cons:* Fragile across query variations, doesn't handle arbitrary test documents or dynamic evaluation sets cleanly.

## Decision
We define an explicit `BaseModelAdapter` interface and provide three implementations:
1. `StubModelAdapter` (default for tests and CI evaluations).
2. `OpenAIModelAdapter` (for hosted production deployments).
3. `OllamaModelAdapter` (for local self-hosted deployments).

Selection is configured via the `MODEL_PROVIDER` environment variable.

## Consequences
- The full evaluation harness can run in GitHub Actions on every pull request within seconds without secrets or API keys.
- Developers can test the entire ingestion and retrieval pipeline locally immediately after cloning.
