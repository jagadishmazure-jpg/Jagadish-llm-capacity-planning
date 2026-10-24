# Implementation guide

How to apply this to a real LLM service. Replace the simulated numbers with your own at each step.

## 1. Measure tokens, per request type

- Log input tokens, output tokens, request type, user and tenant for every call, counted with the
  target model's tokenizer (or the provider's usage field). Never log prompt text to do this.
- Build a histogram per request type, not just one average. Keep p50, p95, p99 and max.
- Re-run [the exercise](exercise.md) on your own traffic each quarter.

## 2. Plan from tokens per second

```bash
capplan estimate --rps 100 --mix chat=0.7,summarization=0.2,code_gen=0.1 \
  --input-price 0.50 --output-price 1.50
```

- Prefill tokens/s = RPS x mean input; decode tokens/s = RPS x mean output.
- Size replicas on whichever binds first: prefill compute, decode batch slots, or KV-cache memory.
  Edit `Hardware` in `capacity.py` with your accelerator's measured prefill rate, time per output
  token, batch size, free memory and your model's KV bytes per token
  (2 x layers x KV heads x head dim x bytes per value).
- Check the largest request fits in one replica's KV cache; reject or route anything that does not.
- Budget on the p95/p99 cost per request as well as the mean.

## 3. Keep the RPS limit, add token limits

- Gateway RPS limit for connection pools and abuse, as before.
- Per-user token bucket (tokens/s with a burst) and a global token bucket set to about 60% of fleet
  prefill capacity, so overload is shed at the door rather than queued.
- Count a request's cost as `input + max_tokens` at admission; refund the unused part afterwards.

## 4. Stop sending whole documents

- Cap input (for example 8,000 tokens). Above it, chunk the document, retrieve the most relevant
  chunks and send those with the question.
- Set `max_tokens` on every call, per request type.

## 5. Budgets, alerts and drift

- Per-tenant monthly budgets with alerts at 50% and 80% and a hard stop or a cheaper model at 100%.
- A drift monitor on rolling average tokens per request against the planning baseline (this repo
  alerts at 2x over a 500-request window). In the simulated month it fired two days before the
  first spend alert. Page on drift, not on the invoice.

## 6. Fair admission

- Serve the user (or tenant) with the least recent token usage first, and cap prompt tokens in
  prefill per user. Short requests then do not wait behind long ones.
- Decide whether fairness is per user or per tenant; per tenant can starve that tenant's light users.

## 7. Prove it

- Replay a day of real token counts through `simulator.run` with your `Hardware`.
- Calibrate against a load test on a real serving engine before trusting the absolute numbers.
