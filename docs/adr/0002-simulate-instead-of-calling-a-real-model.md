# ADR 0002: A seeded simulator instead of a real model

Status: accepted

Context: the repo must run free, offline and deterministically in CI.

Decision: model serving with a discrete-time simulator (chunked prefill, batched decode, KV-cache
admission) on simulated hardware, seeded so every number is reproducible and checked.

Consequences: absolute numbers are illustrative; calibration against a real engine is planned and
listed as such.
