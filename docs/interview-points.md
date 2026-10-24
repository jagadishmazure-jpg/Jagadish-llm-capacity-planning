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
