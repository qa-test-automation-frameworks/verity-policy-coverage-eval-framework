# Dependency exclusions and live-metric quarantine review

The three vulnerability exclusions expired on October 1 and have been removed,
not extended. Their earlier rationale is retained in the archive. No new risk
acceptance or independent human approval is claimed. Scanner findings remain
blocking; a valid empty exclusion file is not a clean dependency result.

The exclusion gate now consumes each date for one ID, rejects duplicate IDs,
malformed lines and invalid calendar dates, and fails on expired or missing dates.
A malformed later date cannot reuse an earlier valid date.

KI-3 still holds out only the two named live clean-control metrics. It now has
an accountable repository-maintainer role, calendar review within 14 days,
expiry within 30 days, and explicit independently reviewed held-out live
promotion criteria. The role is assigned, not recorded as human acceptance.
The original control assertions remain unchanged.

The PR gate and existing weekly adversarial workflow validate the manifest.
They check exact source/test references, actual function-level quarantine
markers, consistent dates and untracked semantic quarantine markers. Removing a
manifest entry does not silently exempt its still-marked test. Metadata validity
cannot establish judge quality or clear a quarantine.

Validation: **32 governance regressions passed** in the isolated all-extras
CPython 3.13 environment, covering invalid/expired/reused dates, duplicates,
missing ownership/promotion fields, excessive windows, broken references,
removed markers, arbitrary source documents and deleted manifest entries.
Ruff checks and formatting passed; both real manifest commands passed on October
4. Initial sandbox execution hit a pytest plugin's local-socket restriction;
the same command passed in the supported execution environment without disabling
plugins or altering test selection.

The semantic-inclusive dependency scan found additional packages beyond the
smaller dev/report scan. Its before/after selected-update facts are retained in
`scans/`; dependency remediation is a separate compatibility-tested change.
Unresolved package findings remain visible. This governance review does not
constitute a security certification or an assessment of every optional deployment.
