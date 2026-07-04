# Calibration Review Workflow

Use this workflow when calibration labels need independent review before thresholds change.

## Sample

- Select 30 cases from `datasets/calibration/labeled.yaml`.
- Include at least four examples for each metric family used by the threshold gate.
- Keep the case ids stable in the review sheet so disagreements can be traced back to source data.

## Reviewers

- Use two or three reviewers who did not author the selected labels.
- Give reviewers only the policy excerpt, candidate response, expected label rubric, and case id.
- Do not include existing model score, existing final label, or previous reviewer notes.

## Capture

Record the review in CSV or YAML with these fields:

| Field | Description |
| --- | --- |
| `case_id` | Calibration case id from the dataset |
| `metric` | Metric family under review |
| `reviewer` | Stable reviewer initials or handle |
| `label` | Reviewer-selected label |
| `confidence` | `low`, `medium`, or `high` |
| `notes` | Short reason for disagreements or ambiguity |

## Promotion Rule

Promote a calibration update only when reviewer agreement is at least 80% on the selected sample
or when every disagreement has a documented rubric clarification. Re-run `make calibrate` after
updating labels and commit the regenerated calibration report with the label change.
