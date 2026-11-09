# Interview points

- **Why did the bill jump with flat RPS?** Cost is per token. The mix shifted: 12% whole-contract
  requests raised average input about 165x and the measured monthly bill 32x.
- **Why did p99 explode?** Prefill demand rose from about 2,300 to about 340,000 tokens/s against a
  fleet that can prefill 36,000. The excess becomes queueing delay that hits everyone.
- **Prefill vs decode.** Prefill is one parallel, compute-bound pass; decode is sequential and
  memory-bound because each step reads the KV cache. Output tokens are priced about 3x.
- **KV cache sizing.** 2 x layers x KV heads x head dim x bytes per token: 128 KiB for an 8B-class
  GQA model, so a 90,000-token prompt holds about 11.8 GB.
- **What binds?** Contract-heavy chat binds on prefill (47 replicas); a code assistant binds on
  decode (38 replicas, prefill would need only 22). Different workloads need different hardware.
- **Why keep RPS limits?** Connection pools, gateways and abuse protection still count requests.
  Add token limits next to them, not instead.
- **Which fix matters most?** Input caps with retrieval cut the bill about 6.7x; fair-share
  admission restores chat latency; global token buckets shed overload; a drift monitor detects
  the change days before the invoice.
- **What surprised you?** A per-user token bucket alone made little difference to latency, and
  per-tenant fairness hurt that tenant's own chat users.
- **What would you not claim?** That the dollar figures are real: the hardware and prices are
  simulated. The ratios and the method are the result.
- **Rent, buy or pay per token?** (example inputs) Owned hardware beats a $0.70/M blended API only
  above about 32% utilisation; always-on cloud GPUs need about 68%. Below that, pay per token.
- **Is power the bottleneck or the cost?** Both, in different ways. Moving electricity from $0.04 to
  $0.30/kWh changes colocation cost per token by about 15%. But a 20 MW connection caps the site at
  12,544 GPUs whatever the budget. PUE decides how much of that connection reaches the GPUs.
- **Why are mining sites converting?** They already have the grid connection, which is the slow part.
  In a mechanical halving what-if (subsidy halves, everything else fixed) the example mining margin per
  MW turns negative, while colocation on the same MW earns more before conversion cost. That is not a
  forecast and not investment advice.
- **How do you keep a cost model honest?** Every input is labelled `example` or `reference` with an
  as-of date, and the loader refuses anything else.

