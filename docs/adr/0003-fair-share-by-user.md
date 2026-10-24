# ADR 0003: Fair-share admission keyed by user, with a per-user prefill cap

Status: accepted

Context: FIFO lets a few huge prompts delay every chat. Fairness keyed by tenant (with a global token bucket) was measured to
push a heavy tenant's own chat users to a p99 of about 31 s.

Decision: order the queue by least recent token usage per user (60 s half-life) and allow at most
8,000 prompt tokens in prefill per user at once. Tenant-level control is handled by budgets.

Consequences: light users are protected even inside a heavy tenant; one user's big job still runs,
just not many at once.
