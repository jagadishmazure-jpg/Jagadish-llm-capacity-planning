# Threat model

Scope: an LLM-backed service planned with this repo, and the repo's own tooling.

## OWASP Top 10 for LLM applications

| Risk | Relevance | Control here |
| --- | --- | --- |
| LLM10 Unbounded consumption (denial of wallet, resource exhaustion) | Central: the incident is unbounded token consumption within RPS limits | Token buckets, input caps, `max_tokens`, tenant budgets, drift monitor, fair share |
| LLM01 Prompt injection | Long pasted documents can carry hidden instructions | Out of scope; retrieval narrows what reaches the model but is not a defence |
| LLM02 Sensitive information disclosure | Contracts contain confidential data | Plan with token counts only; never log prompt text for capacity metrics |

## STRIDE (service)

| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Rotating identities to dodge per-user buckets | Global token bucket and per-tenant budgets also apply |
| Tampering | Client sets a huge `max_tokens` | Server-side output cap per request type |
| Repudiation | Disputed tenant bill | Per-request token accounting per tenant |
| Information disclosure | Metrics pipeline stores prompts | Count tokens, store counts |
| Denial of service | Few users, giant prompts, flat RPS | Token-based admission and fair share |
| Elevation of privilege | Tenant bypasses budget via another tenant's key | Budgets keyed on authenticated tenant |

## Hosting economics calculator (STRIDE)

| Threat | Example | Mitigation |
| --- | --- | --- |
| Tampering | An edited YAML makes one option look cheap with an unlabelled or impossible number | Every number needs a basis; reference numbers need an as-of date; range checks; strict keys |
| Tampering | A malicious YAML tries to build Python objects | `yaml.safe_load` only |
| Repudiation | "Where did this price come from?" | The report lists every reference value and as-of date; everything else is marked example |
| Information disclosure | Real vendor quotes committed by mistake | Keep private quotes in a local copy (`--assumptions my.yaml`); the committed file holds examples only |
| Misuse of output | Example tables read as investment advice or price forecasts | Every page and the CLI say simulated, not advice; the halving section changes one input mechanically; a test bans price-target language in the YAML |

## Repo tooling

No secrets, no network, no cloud resources. gitleaks over full history, CodeQL, Dependabot, pinned
actions, a hashed brand blocklist and docs-drift checks run in CI.
