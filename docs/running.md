# How to run

Requirements: Python 3.11+ and nothing else. No network is needed after `pip install`
(the optional `bpe` extra downloads tiktoken's cl100k encoding once on first use).

```bash
git clone https://github.com/jagadishmazure-jpg/Jagadish-llm-capacity-planning
cd Jagadish-llm-capacity-planning
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # or ".[dev,bpe]"
pytest -q
python scripts/count_tests.py
```

## CLI

| Command | What it does |
| --- | --- |
| `capplan count FILE... [--bpe]` | Words and tokens per file |
| `capplan estimate --rps R --avg-input I --avg-output O` | Tokens/s and the monthly bill from averages |
| `capplan estimate --rps R --mix NAME\|k=v,... [--json]` | Full plan from a sampled mix, with percentiles |
| `--input-price`, `--output-price` | Dollars per million tokens (defaults 0.50 / 1.50); negatives are rejected |
| `capplan simulate --mix NAME [--replicas N --duration S --fixes]` | Run the fleet simulator |
| `capplan bench --write results.json` / `--check results.json` | Regenerate or verify every number |
| `capplan charts` | Regenerate `docs/charts/*.svg` from `results.json` |
| `capplan demo` | The talk's examples and two plans |

Named mixes: `launch_estimate` (chat only), `month_after` (88% chat, 12% whole contracts),
`code_assistant`, `doc_summarizer`. Profiles for custom mixes: `chat`, `contract_qa`, `code_gen`, `summarization`.

## Regenerating the docs

```bash
capplan bench --write results.json     # about 15 s
capplan charts
python scripts/render_docs.py          # README, docs/results.md, docs/exercise.md
python scripts/render_docs.py --check  # what CI runs
```

## Checks CI runs

ruff lint and format, pytest, the printed test count, `capplan demo`, `capplan bench --check`,
the docs-drift check, the hashed brand check and gitleaks over full history. CodeQL runs separately.
