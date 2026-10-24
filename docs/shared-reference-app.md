# Optional shared reference-app assistant

Verity can run an optional, read-only assistant against the synthetic policy and claim API in [`quality-reference-application`](https://github.com/qa-test-automation-frameworks/quality-reference-application). The existing `CoverageAgent`, its seeded/clean profiles, and its offline test path are unchanged. No app session, HTTP request, model call, or extra process is created unless a caller explicitly constructs `ReferenceAppClient` and `SharedAppAssistant`.

The interface lives in `src/sut/shared_app.py`. It reuses the existing `Retriever` and `LLMProvider` contracts, and returns citations resolved only against chunks retrieved for that question. The assistant corpus and tool schema are `v0.2.0`/`v2`. The versioned policy text includes the API-v1 $10,000 and API-v2 $5,000 claim limits; the authenticated workspace tool reads v2 policies and claims, including the server-advertised limit. Fixtures in `datasets/cassettes/retrieval/shared-app*.json` keep citation and authorization tests deterministic without downloading the embedding model or using a provider key.

## Identity and authorization

Construct `ReferenceAppClient` with a configured synthetic identity (`member-a`, `member-b`, or `reviewer`). It creates a session once through the test-only v1 session route and retains that bearer token. The model tool `get_my_reference_workspace` accepts no arguments; Pydantic rejects extra keys, so the model cannot choose a member, policy, or claim. It calls only authenticated v2 policy and claim read endpoints. The application independently scopes those results. `get_claim` exists for direct API authorization tests and is not exposed to the model.

The reference app is a test fixture, not a real insurer or coverage adjudicator. Its synthetic policy records do not describe real-world insurance benefits. Do not attach real member data. Use a unique test namespace and disposable database, and keep `TEST_MODE` enabled only for isolated test deployments because session creation and fixture controls are test-only routes.

## Deterministic checks

The fast tests use an HTTP mock transport and a stub provider; they need no network, app process, or API key:

```bash
uv run pytest tests/unit/test_shared_app.py -q
```

The integration workflow checks out the reference-app source at immutable A07 commit `21af1f41561a6d83ae44933dd36d9daa5e6a6e4c`, builds it, starts it beside a disposable PostgreSQL container, seeds synthetic fixtures, and runs a no-key provider stub. The test verifies both members receive the advertised 500,000-cent v2 limit, member A sees the seeded claim, member B does not, a direct member-B request for member A's claim receives 404, and the assistant answers the v2 limit question with a retrieved citation while refusing to expose another member's records. Cleanup removes the app, network, and database volume. The corrected-source hosted run [39009864840](https://github.com/qa-test-automation-frameworks/verity-policy-coverage-eval-framework/actions/runs/39009864840) passed this no-key authorization/citation integration; the broader Python and image scan failures remain tracked separately under R02.

Run that integration locally when Docker Compose and the repository's pinned Node/npm toolchain are installed:

```bash
export APP_NAMESPACE="verity-a06-local-$(openssl rand -hex 6)"
export APP_SOURCE_SHA="21af1f41561a6d83ae44933dd36d9daa5e6a6e4c"
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

The runtime integration and deterministic assistant checks are not model-quality evidence. Any live answer-quality claim remains gated on the separately budgeted held-out evaluation.
