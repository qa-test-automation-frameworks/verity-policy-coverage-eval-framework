# Supported Python baseline verification

Python 3.13.16 with uv 0.11.25 is the default; Python 3.12.15 is the declared
secondary CI selection. The native metadata excludes unverified 3.14+ minors.
Native uv lock regeneration retains all 196 package name/version pairs; it removes
artifacts/markers for unsupported future minors, without upgrading packages or
changing extras. uv and managed Python metadata are immutable selections; the
helper supplies the publisher's newer checksum-bearing download definitions
because uv 0.11.25's embedded table lacks these security patches.

## Executed checks

- Installed actual CPython 3.13.16 under /tmp using publisher metadata pinned at
  46b84fd0bfec23b72f29e8e2185ba68a65052f48. Global/system interpreters unchanged.
- Normal frozen all-extras installation into an isolated new environment passed.
  Public Chroma model preparation returned 384 dimensions. The existing dependency
  and model caches were available; this is not empty-cache or fresh-clone proof.
- Existing provider-free full suite: 1,714 passed, two expected skips, 112 live
  cases deselected, eight warnings, 191.39 seconds. Ruff checks/format, mypy and
  critical-module coverage passed. Native coverage totals are retained.
- After declaring the supported minor range, frozen resync rebuilt only the project
  metadata and retained dependencies. The documented default bootstrap helper passed.
- Actual CPython 3.14.8 was separately installed and selected for native frozen
  sync dry-run. uv rejected it before dependency installation with exit2 and the
  project requirement `<3.14`. This means unverified for this project, not unsupported
  by Python upstream.
- Actionlint 1.7.7 passed the six changed Python workflows, with optional
  ShellCheck/Pyflakes integrations disabled; helper Bash syntax passed.

## Scope and limitations

The PR matrix explicitly sets UV_PYTHON at job level so later uv run commands keep
its selected interpreter. Local 3.12.15 execution, exact-revision CI and actual
Docker execution remain pending. Publisher registry responses establish container
tags/digests only. The optional paid Promptfoo path selects Node 24.21.0, but its
live behavior is not asserted. No live provider requests were executed.

A direct Python urllib probe of the documented uv installer redirect returned403;
the URL shape is supported by the official installation documentation, while this
session used the already installed pinned uv. It is not claimed as a successful
installer download or clean-machine bootstrap. Native helper/download/quality logs,
coverage, registry responses, metadata selections and source hashes are retained in
`evidence/2026-10-04-runtime/`.

The known Chroma/diskcache/RAGAS dependency advisories remain separate R02/G01 work;
this change does not suppress or declare them repaired. The container model-cache
path across the root/appuser boundary still requires R03 verification; neither
a successful image lookup nor provider-free tests prove offline container behavior.
