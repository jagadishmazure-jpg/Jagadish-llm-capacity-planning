# Words-to-tokens ratio study

Corpus: `corpus.samples(seed=7)`, synthetic text for fictional companies: 200 chat questions,
40 contracts (20-60 clauses), 40 code files (10-40 blocks), 40 articles (10-40 sentences).

| Text type | Words | cl100k tokens (tiktoken 0.14.0) | Tokens per word | Offline approximation | Approx tokens per word | Approx / cl100k |
| --- | --- | --- | --- | --- | --- | --- |
| chat | 1,516 | 1,814 | 1.20 | 1,800 | 1.19 | 0.99 |
| contract | 25,974 | 31,586 | 1.22 | 34,050 | 1.31 | 1.08 |
| code | 8,933 | 23,212 | 2.60 | 28,956 | 3.24 | 1.25 |
| article | 14,802 | 16,849 | 1.14 | 17,951 | 1.21 | 1.07 |

The cl100k column was measured on one machine with the optional `bpe` extra installed; the
approximation columns are deterministic and checked in CI (`ratio_study_approx` in `results.json`).
A test (`test_approx_within_25_percent_of_bpe`) runs whenever tiktoken's encoding is available and fails
if the approximation drifts outside +/-25% on any text type.

What it shows:

- English prose is about 1.1-1.2 tokens per word, so "words x 1.3" is a safe planning rule for prose.
- Code is more than twice as dense in tokens per whitespace-separated word, because symbols,
  indentation and identifiers split into many tokens. Word counts badly underestimate code workloads.
- The approximation is conservative (it overcounts by 0-25%), which is the safe direction for budgets.

How the approximation counts: a run of letters is one token per 8 letters (rounded up), each group of
up to 3 digits is one token, each run of punctuation is one token, each line break is one token.
