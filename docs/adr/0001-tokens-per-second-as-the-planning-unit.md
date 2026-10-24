# ADR 0001: Tokens per second, split into prefill and decode, is the planning unit

Status: accepted

Context: requests per second hides a 4,000x spread in request size and the different costs of
input and output.

Decision: plan capacity and cost from sampled token distributions per request type, separately for
input (prefill) and output (decode), and size replicas on the binding resource. Keep RPS limits
only for plumbing.

Consequences: estimates need token telemetry per request type; the planner reports which resource
binds, which changes hardware choices between workloads.
