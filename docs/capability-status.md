# Capability Status

| Capability | Status | Evidence |
| --- | --- | --- |
| Deterministic replay | Enforced | `make test-deterministic` |
| Unit and framework checks | Enforced | `make test` |
| Defect report generation | Enforced by source data | `make defects-report` |
| Calibration replay | Supported | `make calibrate` |
| Semantic provider run | Informational | `make eval-semantic` |
| Adversarial provider run | Informational | `make redteam` |
