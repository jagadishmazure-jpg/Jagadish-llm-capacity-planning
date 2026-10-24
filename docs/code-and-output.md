# Real code and real output

All output below was produced by running the commands in this repo (Python 3.13, Linux).

## Cost of one request, input and output priced separately

```python
# src/capplan/cost.py
def request_cost(input_tokens, output_tokens, prices=Prices()):
    i = _check("input_tokens", input_tokens)    # rejects negative, NaN, inf, non-numbers
    o = _check("output_tokens", output_tokens)
    return (i * prices.input_per_m + o * prices.output_per_m) / 1_000_000
```

```text
$ capplan demo   (first lines)
"small_request_usd": 5.5e-05,
"large_request_usd": 0.0055,
"large_over_small": 100.0,
"input_tokens_per_s_at_100rps_4000in": 400000.0,
"output_tokens_per_s_at_100rps_500out": 50000.0,
```

## Tokens per second instead of requests per second

```text
$ capplan estimate --rps 100 --avg-input 4000 --avg-output 500
input tokens/s:  400,000
output tokens/s: 50,000
monthly bill:    $712,800.00

$ capplan estimate --rps 1 --avg-input -5 --avg-output 1
error: avg_input must not be negative          (exit code 2)
```

## Capacity plan for the incident mix

```python
# src/capplan/capacity.py (excerpt)
concurrent = rps * mean_out * hw.tpot_s                         # Little's law
kv_bytes = concurrent * mean_ctx * hw.kv_bytes_per_token
by_prefill = math.ceil(prefill_tps / (hw.prefill_tokens_per_s * target_util))
by_decode = math.ceil(concurrent / (hw.max_batch * target_util))
by_memory = math.ceil(concurrent * mean_ctx / (hw.kv_capacity_tokens * target_util))
replicas = max(1, by_prefill, by_decode, by_memory)
```

```text
$ capplan estimate --rps 100 --mix month_after
RPS 100.0 with mix month_after (20,000 sampled requests)
  input_tokens           p50=22  p95=24719  p99=72815  mean=3375.5
  output_tokens          p50=33  p95=431  p99=774  mean=82.0
  service_latency_s      p50=0.826  p95=13.486  p99=22.209
  cost_per_request       p50=6e-05  p95=0.0130365  p99=0.0371535  mean=0.0018108
  prefill tokens/s       337,554
  decode tokens/s        8,200
  KV cache in use        91.8 GB
  replicas               47 (prefill 47, decode 6, memory 3)
  monthly API bill       $469,352.86
  monthly GPU bill       $84,600.00 (self-hosted, simulated rate)
```

The same command with `--mix code_assistant` binds on decode instead (38 replicas: prefill 22,
decode 38, memory 11): code generation writes long answers, so it is limited by output, not prompt size.

## Input cap with retrieval

```python
# src/capplan/fixes.py
def cap_request(r, p):
    inp = r.input_tokens
    if inp > p.max_input_tokens:                 # 8,000 by default
        chunks = math.ceil(inp / p.chunk_tokens) # 512-token chunks
        inp = min(chunks, p.top_k) * p.chunk_tokens + p.question_tokens   # send top 4 + the question
    out = min(r.output_tokens, p.max_output_tokens)                       # max_tokens = 512
```

```text
$ capplan simulate --mix month_after --duration 10 --fixes   (excerpt)
"cap_actions": {"unchanged": 904, "retrieved": 68, "retrieved+output_capped": 33, "output_capped": 6},
"avg_input_tokens": 305.7,
"chat_latency_s": {"p50": 0.815, "p95": 1.699, "p99": 2.489},
```

## Token counter

```text
$ printf 'The Supplier shall deliver the Goods within 30 business days.\n' > s.txt
$ capplan count s.txt
s.txt: words=10 tokens=12
$ capplan count --bpe s.txt        # real cl100k_base via tiktoken
s.txt: words=10 tokens=12
```
