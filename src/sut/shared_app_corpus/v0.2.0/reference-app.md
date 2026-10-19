# Reference application policy and claim workflow

## Policy version

The reference application ships synthetic policy records tagged `v0.1.0`. A policy record is a versioned test fixture, not an insurance contract or a coverage determination. The API exposes only policies visible to the authenticated synthetic identity.

## Claim records

Claims belong to the member who submitted them. Members may inspect their own claims; reviewers may inspect claims in the isolated test namespace. A claim's status and amount are application data, not a decision about real coverage or payment.

## Privacy boundary

The caller's session establishes identity. Tool arguments must not contain a member identifier, policy identifier, or claim identifier. Requests for another member's records must be denied by the application's authorization layer even if a model is asked to disclose them.
