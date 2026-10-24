# Limitations and known failures

- **Simulated hardware and model.** Prefill rate, time per token, batch size, memory and prices are
  assumptions. Absolute dollars and seconds are illustrative; ratios between scenarios are the point.
- **The 80x is not reproduced.** With a 12% share of whole-contract requests the measured bill
  multiplier is 32x (29.2x in the planner's sample). The share sweep shows 80x needs roughly 30-40%
  whole-contract traffic in this model. We did not tune the mix to hit the talk's number.
- **p99 depends on run length.** In the incident the queue grows without bound, so the measured p99
  (613 s over a 60 s burst) would be larger for a longer burst. It is a symptom of overload, not a
  steady-state figure.
- **Token-planned fleet still has a slow tail.** Even with 47 replicas the overall p99 is about 23 s,
  because a single 90,000-token prompt takes about 7.5 s to prefill on one replica and its answer
  then decodes at 25 ms per token. Chat p99 is restored (2.4 s); the contract tail needs prefill
  splitting across replicas (planned) or retrieval.
- **Per-user token bucket alone does not help latency** (scenario 7 is worse than scenario 4):
  heavy users are rejected only after their burst allowance, and the backlog has already formed. It
  is a fairness and abuse control, kept visible as a known weak fix.
- **Fair share by tenant hurts that tenant's light users.** Keyed by tenant, a heavy tenant's chat
  users wait behind its own contracts. The default keys fairness by user.
- **Retrieval quality is not modelled.** The cap assumes the top 4 chunks answer the question.
  Real retrieval can miss; measure answer quality before relying on it.
- **The offline token counter overcounts** by 0-25% against cl100k (most for code). Other model
  tokenizers differ again; always count with the target model's tokenizer.
- **Not modelled:** prefix caching, speculative decoding, quantised KV cache, preemption and swapping,
  network time, autoscaling delays, retries.
- All tests are regression checks on synthetic data written alongside the code; they show the code
  does what it says, not that the numbers match any real deployment.
