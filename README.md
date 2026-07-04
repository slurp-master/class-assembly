# Syncademy raid setup creator

Turns MMO raid signups (Discord reactions) into balanced 8-person groups that satisfy a
fixed role composition and have a raid leader each.

> For the full goal, domain rules, and design decisions, see [AGENTS.md](AGENTS.md).

## Install

Uses [uv](https://docs.astral.sh/uv/) for dependencies.

```bash
uv sync            # runtime deps
uv sync --group dev # + dev deps (pytest), for running tests
```

## Pipeline

Two steps, run in order:

1. **Parse signups** — reads the per-role Discord reaction exports in `data/<event>/*.json`
   and writes `data/010_reactions/reactions.csv`.

   ```bash
   uv run python 010_parse_reactions.py
   ```

   (Raid leaders are a hard-coded `global_name` list inside this script — edit it per event.)

2. **Create setup** — reads `reactions.csv`, builds and balances groups, writes
   `data/020_setup/setup.csv`, and prints a per-group preview to the console.

   ```bash
   uv run python 020_create_setup.py [--seed N] [--phantom-rl N]
   ```

   - `--seed N` — random seed for reproducibility; re-run with different seeds to get
     alternative setups and keep the best.
   - `--phantom-rl N` — allow up to `N` groups to form without a real raid leader (default `0`).

## Tests

```bash
uv run pytest
```
