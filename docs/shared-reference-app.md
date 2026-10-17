# Optional shared reference-app assistant

Verity can run an optional, read-only assistant against the synthetic policy and claim API in [`quality-reference-application`](https://github.com/qa-test-automation-frameworks/quality-reference-application). The existing `CoverageAgent`, its seeded/clean profiles, and its offline test path are unchanged. No app session, HTTP request, model call, or extra process is created unless a caller explicitly constructs `ReferenceAppClient` and `SharedAppAssistant`.

The interface lives in `src/sut/shared_app.py`. It reuses the existing `Retriever` and `LLMProvider` contracts, and returns citations resolved only against chunks retrieved for that question. The versioned fictional policy text is in `src/sut/shared_app_corpus/v0.1.0/`; the function schema has version `v1`. The fixture in `datasets/cassettes/retrieval/shared-app.json` makes the citation path deterministic without Chroma, ONNX downloads, or a provider key.

## Identity and authorization

Construct `ReferenceAppClient` with a configured synthetic identity (`member-a`, `member-b`, or `reviewer`). It creates a session once and retains that bearer token. The model tool `get_my_reference_workspace` accepts no arguments; Pydantic rejects extra keys, so the model cannot choose a member, policy, or claim. The tool only calls the app's authenticated `GET /api/v1/policies` and `GET /api/v1/claims` endpoints. The application independently scopes those results. `get_claim` exists for direct API authorization tests and is not exposed to the model.

The reference app is a test fixture, not a real insurer or coverage adjudicator. Its synthetic policy records do not describe real-world insurance benefits. Do not attach real member data. Use a unique test namespace and disposable database, and keep `TEST_MODE` enabled only for isolated test deployments because session creation and fixture controls are test-only routes.

## Deterministic checks

The fast tests use an HTTP mock transport and a stub provider; they need no network, app process, or API key:

```bash
uv run pytest tests/unit/test_shared_app.py -q
```

The integration workflow checks out the reference-app source at `e9f438e06a2b092dccfc6e9ab1820ff2562ddad7`, builds it, starts it beside a disposable PostgreSQL container, seeds synthetic fixtures, and runs a no-key provider stub. The test verifies member A sees the seeded claim, member B does not see it in the workspace, a direct member-B request for member A's claim receives 404, and an assistant query cannot add another member's records to the fixed-identity tool result. It also verifies the retrieved privacy citation. Cleanup removes the app, network, and database volume.

Run that integration locally when Docker Compose and the repository's pinned Node/npm toolchain are installed:

```bash
export APP_NAMESPACE="verity-a06-local-$(openssl rand -hex 6)"
export APP_SOURCE_SHA="e9f438e06a2b092dccfc6e9ab1820ff2562ddad7"
export APP_PORT=4300
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export TEST_CONTROL_TOKEN="$(openssl rand -hex 32)"
docker compose -p verity-a06 -f ../quality-reference-application/compose.yaml up --build -d
curl --fail http://127.0.0.1:4300/health/ready
VERITY_REFERENCE_APP_URL=http://127.0.0.1:4300 \
VERITY_REFERENCE_APP_CONTROL_TOKEN="$TEST_CONTROL_TOKEN" \
  uv run pytest tests/integration/test_shared_app_runtime.py -q
docker compose -p verity-a06 -f ../quality-reference-application/compose.yaml down --volumes --remove-orphans
```

The runtime integration and deterministic assistant checks are not model-quality evidence. Any live answer-quality claim remains gated on D05's separately budgeted evaluation.
