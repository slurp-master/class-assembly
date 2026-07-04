---
name: step-010-is-temporary
description: 010_parse_reactions.py is throwaway scaffolding — don't test or over-harden it
metadata:
  type: project
---

`010_parse_reactions.py` (Discord reaction JSON -> reactions.csv) is **temporary**. The
real reaction-parsing functionality lives elsewhere and may be used directly later, at
which point 010 could be removed.

**Why:** don't invest in unit tests or heavy hardening for it — that effort would be
thrown away. Bug fixes / small improvements are fine; automated tests are not worth it.

The downstream pipeline (loader, [[fat-models-preference]] grouper, balancer) is the
durable part and *should* be well-tested.
