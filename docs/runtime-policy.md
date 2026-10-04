# Supported runtime and tool policy

Python3.13.16 with uv0.11.25 is the default baseline, pinned in `.python-version`,
contributor bootstrap, CI and container tags/digests. Python3.12.15 is the secondary
CI compatibility baseline. Project metadata permits the supported3.12/3.13 minors
and rejects other minors; this is not a claim that every patch has been tested.
Use the pinned security patches for the supported bootstrap path.

The [Python release notice](https://blog.python.org/2026/10/python-31022-31117/)
and [lifecycle table](https://devguide.python.org/versions/) were checked. Python3.14
and later are outside the declared compatibility matrix until wheels, optional
extras and actual tests are verified. uv is pinned for reproducibility, not claimed
latest. Its built-in download table predates these Python patches; the bootstrap
helper uses checksum-bearing
[publisher metadata at46b84fd](https://github.com/astral-sh/uv/blob/46b84fd0bfec23b72f29e8e2185ba68a65052f48/crates/uv-python/download-metadata.json).
Updating that commit/tool/runtime requires independent verification.

On Linux/macOS with the pinned uv installed, run from the repository root:

```sh
make install
make prepare-embeddings
make test-deterministic
```

`make install` provisions the declared interpreter and uses frozen all-extras
selection, matching the PR gate. Install uv0.11.25 through an
[official pinned installer or release artifact](https://docs.astral.sh/uv/getting-started/installation/).
No provider key is needed for this replay path. Dependency and first model downloads
need network access; real embedding/model tests are not inherently offline.
Adversarial CI retains its explicit dev/report extras and defaults to no live spend.
Live/paid commands, mutation tooling and Docker are separate paths.

The PR matrix sets UV_PYTHON for every step so the secondary interpreter remains
selected by later uv run commands instead of silently reverting to `.python-version`.
To reproduce the secondary path, keep its explicit selection on every command:

```sh
UV_PYTHON=3.12.15 bash scripts/install-python.sh 3.12.15
UV_PYTHON=3.12.15 uv sync --frozen --all-extras
UV_PYTHON=3.12.15 make test-deterministic
```

The default remains Python3.13.16.

Container Python/uv tags are pinned by verified publisher registry digests. Local
Docker is unavailable, so tag resolution is not execution proof. Frozen dependency
selection and model preparation remain distinct from vulnerability clearance.
Current Chroma/diskcache/RAGAS advisories are not resolved by this runtime change;
no expired exclusions are renewed. The optional Promptfoo job now selects
Node24.21.0; its paid runtime behavior is unverified until an authorized live run.
