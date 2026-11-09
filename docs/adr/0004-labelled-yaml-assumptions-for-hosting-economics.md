# ADR 0004: Labelled YAML assumptions for hosting economics

Status: accepted

Context: hosting cost comparisons are easy to bias. A made-up GPU price or PUE can look like a fact
once it sits in a table. The hosting calculator needs dozens of inputs, most of them prices that
change every month and differ by provider.

Decision: keep every input in one YAML file (`assumptions/hosting.yaml`). Every number is a mapping with
`value` and `basis`. The basis is `example` (made up, plausible) or `reference` (a typical published
industry figure; needs an `as_of` date). The loader rejects bare numbers, unknown keys, missing keys and out-of-range values.
The report lists every reference value and its as-of date. The generated tables in the docs are checked in CI.
This adds one runtime dependency, PyYAML, pinned to an exact version and loaded with `safe_load` only.

Consequences: anyone can swap in their own quotes without touching code, and readers can always see
which figures are invented. The calculator cannot quietly fall back to a default. The cost is a more
verbose YAML file and one dependency in a package that had none.
