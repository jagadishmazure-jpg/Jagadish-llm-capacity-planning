# Plain-words explainer

## Tokens

A model does not read words. It reads **tokens**: pieces of text from a fixed vocabulary. Common
short words are one token; long or rare words, numbers and punctuation split into several. In this
repo's corpus, ordinary English is about 1.2 tokens per word and source code about 2.6 tokens per
"word" (measured with the cl100k encoding; see [tokens.md](tokens.md)). Every price and every
throughput number for an LLM is per token.

## Prefill and decode

Serving one request has two phases.

- **Prefill** reads the whole prompt in one pass. All prompt tokens are processed in parallel, so
  the GPU's arithmetic units are busy and the work per token is cheap. Its cost grows with prompt
  length. It decides the time to first token.
- **Decode** writes the answer one token at a time. Each step produces a single token per
  sequence and must read the cached state of every earlier token. The GPU spends most of its time
  moving memory rather than computing, which is why output tokens are slower and usually priced
  about three times higher.

In this repo's simulated hardware, prefill runs at 12,000 tokens/s per replica and decode at
25 ms per token per sequence, 64 sequences at once.

## KV cache

To avoid recomputing the past at every decode step, the server stores, for every token seen so far,
two vectors per layer (the "keys" and "values" of attention). That store is the **KV cache**. Its
size is tokens x layers x 2 x KV heads x head size x bytes. For the simulated 8B-class model with
grouped-query attention that is 131,072 bytes (128 KiB) per token. A 90,000-token contract therefore
holds about 11.8 GB of GPU memory for as long as its answer is being written, and a replica with
about 56 GB free for cache can hold roughly 427,000 tokens in total. Long prompts crowd out other users.

## Why requests per second misleads

Requests per second counts arrivals, not work. With the same 100 RPS:

- a chat-only mix averages about 23 input and 34 output tokens: about 2,300 prefill tokens/s; a
  fleet of 3 simulated replicas is enough;
- a mix where 12% of requests are whole contracts averages about 3,400 input tokens: about 340,000
  prefill tokens/s; the planner needs 47 replicas.

The RPS limit never fires in either case. The queue in front of the GPUs grows instead, and
because queueing delay hits everyone, short chats end up waiting behind contracts. That is how a
p99 goes from about 2.5 seconds to minutes in the simulation while the RPS dashboard stays green.

## Averages vs percentiles

Token counts have a long tail. In the incident mix the median input is 22 tokens while the p99 is
over 72,000. Planning on the mean hides that one request in a hundred is three thousand times larger
than the typical one, and those requests set both the KV-cache peak and the latency tail. The
planner reports p50, p95 and p99 for tokens, cost and service time.

## What to limit instead

Keep RPS limits for plumbing. Add limits in tokens: per-user and global token buckets, a cap on
input size with retrieval of relevant chunks instead of whole documents, a `max_tokens` cap on
output, per-tenant spend budgets, a monitor on average tokens per request, and admission that
shares capacity fairly between users.
