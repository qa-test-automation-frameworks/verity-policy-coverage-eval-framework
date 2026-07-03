## Token & Cost Summary

| Label | Calls | Prompt tok | Completion tok | Total tok | Cost (USD) |
|-------|------:|-----------:|---------------:|----------:|-----------:|
| `agent-first-turn` | 55 | 41,365 | 3,412 | 44,777 | $0.008252 |
| `agent-second-turn` | 10 | 8,205 | 1,044 | 9,249 | $0.001857 |
| **Total** | **65** | **49,570** | **4,456** | **54,026** | **$0.010109** |

_Recomputed from the original run's token counts after adding `gpt-4o-mini` to
`verity.cost._PRICE_TABLE`; `openrouter/openai/gpt-4o-mini` (the model used for
this run) previously had no price entry and rendered as an unpriced-model
placeholder rather than a confirmed free rate._
