# Purpose

## The problem

Teams size LLM services the way they size web services: pick a requests-per-second limit, multiply
by a per-request cost, buy enough servers. That works when every request costs about the same. LLM
requests do not. A one-line question and a pasted 60-page contract are both "one request", yet the
second can need thousands of times more compute, memory and money.

## Who this is for

- Engineers and architects who have to give a cost and capacity number before launch.
- SRE and platform teams who need limits and alerts that catch a change in request size, not just volume.
- Interviewers and candidates working through LLM system design questions.

## The source scenario, in our own words

A public system design talk (AI system design series, episode on rate limiting) describes a support
chatbot that was fixed after an earlier incident and relaunched. A month later two things had gone
wrong. The invoice was roughly eighty times the forecast, and the slowest one percent of ordinary
requests now took about thirty seconds instead of under half a second. Nothing obvious had changed:
the limit of 100 requests per second was never breached, and both the number of users and the
number of requests per user were steady.

The cause was the size of each request. At launch nearly all traffic was short back-and-forth
chat. After the relaunch some people pasted entire contracts and asked questions about them, so a
few requests carried around ninety thousand input tokens and the average grew into the thousands.
The team's estimate had assumed short chats and so did its limits.

The talk's lessons, restated:

1. The unit of work is the token. Words are a poor proxy and requests are a worse one.
2. Input and output tokens are different work. The prompt is processed in one parallel pass
   (prefill); the answer is produced one token at a time (decode), and each new token has to look
   back over everything before it, which is what the KV cache stores. Decode is memory-hungry and
   is priced higher, for example $0.50 per million input tokens against $1.50 per million output.
3. A tiny request (about 20 tokens in, 30 out) costs a few thousandths of a cent. A request with
   8,000 in and 1,000 out costs about a hundred times more.
4. Keep the requests-per-second limit, because connection pools, gateways and abuse protection
   still need it, but derive capacity and cost from tokens per second: 100 RPS with an average of
   4,000 input tokens is 400,000 input tokens per second, and with 500 average output tokens it is
   50,000 output tokens per second.
5. Different products have different token shapes (chat, code generation, summarisation), so each
   needs its own estimate. The talk asks viewers to measure average input and output tokens for a
   few request types and chart them; [exercise.md](exercise.md) does that.

## What this repo adds

The talk gives the reasoning; this repo turns it into code you can run, with distributions and
tails instead of averages, a simulator that shows how latency collapses, and measured fixes.
