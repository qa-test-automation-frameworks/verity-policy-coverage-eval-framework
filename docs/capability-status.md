# Capability Status

| Capability | Status | Evidence |
| --- | --- | --- |
| Deterministic replay | Enforced | `make test-deterministic` |
| Unit and framework checks | Enforced | `make test` |
| Defect report generation | Enforced by source data | `make defects-report` |
| Calibration replay | Supported | `make calibrate` |
| Semantic provider run | Informational | `make eval-semantic` |
| Adversarial provider run | Informational | `make redteam` |

## Feature currency review — 2026-10-16

| Capability | Current implementation | Official support checked | Benefit and compatibility risk | Decision and proof |
| --- | --- | --- | --- | --- |
| Local retrieval and embeddings | `chromadb.PersistentClient` with Chroma's default local ONNX embedding function; source and chunk metadata are retained by the retriever. | [Chroma client documentation](https://docs.trychroma.com/reference/python) documents persistent, ephemeral and server clients. | A local persistent client keeps the demo reproducible without a managed service. It does not demonstrate remote multi-tenant security or distributed scale. | **Retain local mode.** Exact Docker check `38932690221` built the pinned image and passed the non-root, no-network ONNX smoke; Trivy then found 44 HIGH Debian findings and 12 Python findings (8 HIGH, 4 CRITICAL). Keep the app claim scoped to local/single-node mode. Four Chroma advisories remain an unsuppressed R02 blocker. |
| Tool schemas and structured results | Pydantic argument models, explicit allowlisted tool dispatch, response validation and domain guardrails live in the SUT rather than a provider-managed agent loop. | LiteLLM now documents [structured output](https://docs.litellm.ai/docs/harness/structured_output) and a [tool loop](https://docs.litellm.ai/docs/harness/tool_loop); Pydantic remains the schema boundary used here. | Provider harnesses can reduce orchestration code, but would couple seeded defects, replay tests and tool policy to a changing SDK execution path. | **Retain explicit orchestration.** Existing unit, deterministic and adversarial gates exercise malformed arguments and rejected tool actions; do not claim LiteLLM harness compatibility. |
| Semantic evaluation | DeepEval and RAGAS adapters implement text faithfulness, context precision/recall and answer relevancy; paid calls are separate from replay tests. | [RAGAS releases](https://github.com/vibrantlabsai/ragas/releases) list 0.4.3 as latest; [RAGAS metric documentation](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) describes current metric families. | The adapters show complementary evaluation methods. Live scores remain provider/model/dataset specific and require independent calibration. | **Retain text metrics; defer new metric families.** D05 still needs held-out independent labels and an authorized live run. Do not pass arbitrary retrieved URLs to the vulnerable multimodal helper. RAGAS 0.4.3 and transitive DiskCache findings remain unsuppressed in [the native scan](security/scans/2026-10-16-after-transitive-fixes.json). |
| Provider abstraction and observability | LiteLLM adapters, deterministic cassette replay, explicit live-test markers and OpenTelemetry tracing keep provider execution separate from local evidence. | [LiteLLM SDK documentation](https://docs.litellm.ai/docs/) describes provider normalization, retries, fallbacks and callbacks. | A single provider interface simplifies controlled substitution; retries, provider routing and callback changes can alter cost, latency and replay semantics. | **Retain the explicit adapter and replay/live split.** No provider-routing or prompt-caching behavior is claimed without an authorized live comparison. |

The review records the current feature boundary rather than adding new AI
harnesses or providers. Dependency vulnerabilities and independent live
calibration remain visible blockers; local deterministic evidence does not
clear either one.
