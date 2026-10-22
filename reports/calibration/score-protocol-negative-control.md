# Score Protocol Negative Control

This retained no-provider regression artifact represents a malformed
`Score: 100` input under calibration protocol v2. Runtime reports keep the
case identity and sanitized diagnostic but omit the raw judge response.

**Status:** FAILURE — INCOMPLETE  
**Cohort:** synthetic parser control  
**Planned:** 1  
**Attempted:** 1  
**Completed:** 0  
**Invalid:** 1  
**invalid_output_count:** 1  
**Valid agreement / MAE observations:** 0

| Case | Metric | Score | Outcome |
|---|---|---:|---|
| `score-protocol-invalid-100` | completeness | — | `score_protocol_format_mismatch:length=10` |

The invalid response remains in the planned denominator. It is excluded from
agreement and MAE, is not converted to a zero or false negative, and forces an
incomplete report even if every valid case agrees. The regression test also
checks that the unredacted response does not appear in the rendered report.

This artifact demonstrates parser disposition only. It is not a provider run
or a judge-performance measurement.
