# Versioned claim submission limits

## Claim submission limits

API v1 remains supported with its existing maximum of 1,000,000 USD cents ($10,000.00). API v2 has a maximum of 500,000 USD cents ($5,000.00). A v2 policy response supplies `claimAmountLimitMinor`; clients must use the limit returned by the API. A claim above the limit for its API version is rejected. This is synthetic test behavior, not an insurance coverage or payment decision.
