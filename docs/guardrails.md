# Guardrails

## In the model of the service

| Control | Where | What it stops | Measured effect (simulation) |
| --- | --- | --- | --- |
| RPS limit (kept) | `simulator.run` | Connection floods, abuse | Holds in every run; under 1% of arrivals over the limit due to Poisson bursts |
| Per-user token bucket | `fixes.TokenBucket` | One user sending huge prompts back to back | Rejects 438 heavy-user requests in scenario 7, but on its own does not fix latency |
| Global token bucket | `fixes.TokenBucket` | Load above what the fleet can prefill | Set to 60% of fleet prefill capacity in scenario 8 |
| Input cap + retrieval | `fixes.cap_request` | Whole documents in the prompt | Average input from about 3,700 to about 360 tokens; bill about 6.7x lower |
| `max_tokens` | `fixes.cap_request` | Runaway answers | Output capped at 512 |
| Tenant budget with 50/80/100% alerts and hard stop | `fixes.TenantBudget` | Spend surprises | Heavy tenant stopped on day 3 of the simulated month; others never stopped |
| Cost-drift monitor | `fixes.DriftMonitor` | Silent shift in tokens per request | Fires on day 2, before the first spend alert on day 4 |
| Fair-share admission | `fixes.FairShareQueue` | Short requests stuck behind long ones | Chat p99 from 52.7 s to 3.7 s with caps on the same fleet |

Exact figures are in the generated results table in the README.

## In the tooling

- Every cost input (prices, token counts, RPS, budgets, charges) rejects negative, NaN, infinite,
  boolean and non-numeric values with a clear error; the CLI exits with code 2.
- Mixes must use known profiles with non-negative shares summing to 1.
- Simulation and sampling are seeded; CI fails if any number in `results.json` changes without
  being regenerated, and if docs drift from it.
- No network calls, no credentials, no cloud resources. gitleaks scans full history; a hashed
  brand blocklist keeps real company names out.
