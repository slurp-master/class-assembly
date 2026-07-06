# Project: Raid group setup creation

Automation for an MMO-RPG raiding community. Members sign up for events by reacting
to a Discord message (one reaction per role they are comfortable with). The tool takes
those signups and combines people into balanced raid groups that satisfy a fixed role
composition, so an organizer doesn't have to do it by hand.

## Pipeline

1. `010_parse_reactions.py` — parses the per-role Discord reaction JSON exports
   (`data/<event>/*.json`) into a single `data/010_reactions/reactions.csv`. Each row is
   a player; boolean columns mark which roles they signed up for plus `backup` and
   `raid_leader`. Raid leaders are supplied out-of-band (a hard-coded list of
   `global_name`s in the script, *not* present in the reaction JSON) and matched by name;
   the script warns if any named leader isn't found among signups.
   - The `check` reaction is an **attendance confirmation**, not a role — it exists to
     confirm someone actually signed up rather than mis-clicking. The script warns about
     anyone who reacted with *anything* (a party role or `backup`) but did *not* check in
     (kept in the CSV; warn-only). The loader never treats `check` (or `backup`/
     `raid_leader`) as a role.
2. `020_create_setup.py` — loads players from `reactions.csv`, assembles groups
   (greedy constructor), balances them by experience (swap-based local search), and
   writes `data/020_setup/setup.csv` plus a human-readable console preview.

## Domain rules

- Group size is **8**, composition is **fixed**: 2 tank, 1 pure healer, 1 shield healer,
  4 DPS. DPS come in three flavors: melee, ranged, caster.
- A player may sign up for **one or more** roles ("flexing"). A group only needs to be a
  **viable combination** — one whose signups *can* cover the required composition. The
  tool does **not** assign a concrete role to each player in its output: players decide
  what they actually play once they see their group and who they're with.
- Internally the grouper tracks a *tentative* role per player. This is an implementation
  detail that makes composition validation and composition-safe balancing swaps possible;
  it must **not** appear in any output (CSV or console).
- **DPS flavor rule:** each group should have **at least one of each DPS flavor**
  (melee + ranged + caster), with the 4th DPS being any flavor. This is a **hard** rule
  *when achievable*. To maximize the number of complete groups, a group may **relax**
  to fewer flavors (e.g. 2 melee + 2 caster) — but *only when stuck*, i.e. no strict
  candidate exists at fill time. Every relaxed (non-standard) group must emit a warning.
- **Raid leader:** every group needs **at least one raid leader** to start. A raid leader
  is an ordinary member who fills a normal composition role but also organizes and shot-
  calls the group. It is a **hard** requirement *on top of* role composition — not a
  composition slot, so it can't be modeled as just another role. The grouper handles it
  RL-first: it seats one raid leader (into any composition role they can fill) before
  ordinary members compete for slots, and it **reserves** the remaining raid leaders so
  ordinary fills don't drain the pool below what later groups need. Raid leaders cap the
  group count just like tanks and healers do.
  - **Phantom raid leaders:** setups are made ~a day before the event, so a group may be
    intentionally formed *without* a real raid leader, hoping one is found in time. This
    is opt-in via `--phantom-rl N` (default 0): once real raid leaders are exhausted, up
    to `N` further groups may form with a **placeholder** raid leader occupying one of the
    8 composition slots. Placeholders are drawn from a cycled name list (`PHANTOM_RL_NAMES`,
    e.g. "Raidingway", "Teachingway", "Wipingway") and are treated as flex players (can
    fill any role). The placeholder is seated first, exactly like a real RL, before ordinary
    role-filling. Phantom groups are flagged in both outputs: a `?` in the `RL` column in
    the console table, and `group_needs_rl = True` in the CSV. Placeholder players are
    never swapped during balancing (frozen in place), and pairs logic ignores them entirely.
- **Maximize the number of complete groups.** Players who don't fit go to the bench.
- **Backups are bench-first.** Players who opted into `backup` are the natural bench
  candidates: the grouper fills every slot from regular signups first and only pulls in a
  backup when no regular can cover a slot (including the raid-leader seat). Backups still
  count toward the group-count cap — bench-first is an *ordering* preference, not an
  exclusion, so a backup will be used if a group genuinely needs them.

## Experience & balancing

- Each player has a **numeric experience** value. Groups should be balanced so total
  group experience is comparable (avoid stacking all veterans in one group).
- Real experience data is **not wired up yet**. For now, experience is a **proxy =
  number of roles the player can fill** (more flexible players tend to be more
  experienced). Real indicators exist and will be added later.
- Plumbing requirement: the pipeline carries experience as an explicit **numeric field**,
  produced by a **single provider function** (currently returns `num_roles`). The
  balancer reads that field, never `num_roles` directly — so swapping in a real source
  later touches exactly one place.
- **Balancing only redistributes already-grouped players; the bench is frozen.** Swaps
  happen between formed groups, never between a group and the backup pool. This is
  deliberate: getting every regular signup *into* a group takes priority over group
  balance, so balancing must never pull a grouped player out to the bench to even out
  experience. (A future bench↔group swap feature would trade off against this priority.)

## Approach

Greedy constructor + swap-based local search. No need for a provably optimal solution;
"good enough" that a human can eyeball and hand-tweak is the goal. Being able to re-run
with different seeds to get alternative setups is valuable — the initial solve is the
time-consuming part, not evaluating a candidate.

Because it's a single greedy pass, re-running with different `--seed` values can surface
alternative (sometimes better-balanced) setups — the intended way to explore options.

**Raid-leader seating is capability-aware.** A DPS-only raid leader is seated into a
concrete DPS flavor (the internal `'dps'` slot placeholder is resolved), and within each
group the *most constrained* available raid leader is seated first. This front-loads
inflexible leaders (e.g. a caster-only RL) so they aren't stranded once their only viable
slot is gone — without it, such a leader could be left over and cost the group entirely.

Balancing swaps are constraint-preserving — they only exchange two players when each can
play the other's tentative role *and* neither group loses its required raid leader.

## Output

- `data/020_setup/setup.csv` — canonical, machine-readable; imported into other systems.
  Columns: `group_id`, `global_name`, `raid_leader`, `group_needs_rl`, then a boolean per
  role (role availability, not an assignment). Bench players get `group_id = backup`.
- Console table — human-readable preview for the operator to sanity-check a run. One
  table per group (its own header), a `★` in the `RL` column marks raid leaders, `✓`
  marks role availability, emojis stripped from names for terminal legibility. Phantom
  groups are headed with a "NEEDS RAID LEADER" note.

Keep **both**; they serve different consumers. Neither shows an assigned role.

## Pairs

Players who want to end up in the same group can be registered as a **pair**. Pairs are
stored in `data/000_pairs/pairs.csv` (columns: `name_1`, `name_2`, both `global_name`
values). The file is mandatory — an exception is raised if it is absent.

### Semantics

- A pair is **community-wide and persistent**: it grows independently of event signups.
  Many pairs will have one or both members absent from any given event.
- A pair is **active for an event** only when **both** members signed up. If only one
  signed up, that player competes as unpaired (no warning to the operator — this is
  expected). If neither signed up, the pair is silently skipped.
- **RL × RL pairs are forbidden** and raise a `ValueError` at load time. One RL + one
  non-RL is allowed.

### Placement rule

Pairs are a **best-effort preference**, not an absolute guarantee. There is no forced
pre-seating; instead, candidate selection in `_pick` and `_candidates_for` is biased
toward keeping pairs together via a three-level priority:

1. **Partner already in this group** — if a candidate's pair partner is already seated in
   the group being filled, that candidate is preferred above all others for the current
   slot.
2. **Partner still available** — if a candidate's pair partner is still in the pool,
   prefer them next. This front-loads paired players so their partners have more
   opportunities to follow into the same group.
3. **Most constrained** (fewest available roles) — the normal constrained-first tiebreak.
4. **Random tiebreak** among candidates that share the same top three values (seeded for
   reproducibility).

Additionally, the bench-first rule is relaxed for backups: if a backup's pair partner is
already seated in the group being filled, that backup is admitted as a candidate even when
non-backup candidates also exist (`_candidates_for`). This prevents the bench-first filter
from silently stranding backup pairs.

This approach never blocks group formation — no slot is ever reserved or held for a
partner, so a group can always be completed regardless of pair state.

### Violated pairs

After all groups are assembled, `_detect_violated_pairs` scans every active pair and
records any where the two members ended up in different groups or one/both on the bench.
Each canonical pair appears **at most once** in `assembly.violated_pairs`. The caller
(`020_create_setup.py`) logs all violated pairs as warnings at the end of the run.

### Balancer constraint

`swap_members_for_balance` accepts an optional `pairs` dict. Any swap that would move
one half of a pair to a different group while the other half stays is rejected
(`_swap_splits_pair`). Pair integrity takes priority over experience balance.

**Known limitation — zero shared roles:** If two paired players share no roles at all
(e.g. one is pure/shield-only, the other is caster-only), they fill entirely different
composition slots and preseat can never trigger for them from each other. They will always
violate. A pre-group-seeding step that picks pairs first and builds the group around them
would fix this, but requires a larger architectural change.

**Deferred:** swapping two paired players together for two players from another group
(or another pair) would allow balance improvement without splitting pairs — not yet
implemented.

## Bench fairness

The constrained-first ordering has a known fairness cost: the most flexible regular
player(s) — those with the most available roles — absorb involuntary bench spots
deterministically. With the current event data it is always the same person (Eclipser,
6 roles). Single-role players and raid leaders never bench by design.

`020_create_setup.py` already warns about this at the end of each run
(`Forced on bench (N): ...`), so the operator can intervene manually (e.g. swap the
repeatedly-benched player in by hand, or try different seeds).

A proper algorithmic fix would require tracking bench history across past events and
using it as a tiebreaker in `_pick` — deliberately not implemented; handle outside the
tool for now.


## Code style
Use single quotes in code.
Line length limit: 120.

**Fat models.** Business objects (`Player`, `Group`, `Assignment`) own their logic. Any
function that takes a single object and only touches its internals belongs on the class
as a method/property (e.g. `Group.experience`, `Assignment.can_swap_with`). Functions
operating over a *collection* of objects (e.g. imbalance across all groups, the swap
search) stay as free functions. This keeps logic discoverable and eases unit testing.


## Tests

Tests use **pytest** (a dev dependency) — plain `assert` statements get full value/diff
output on failure. No `unittest`. Conventions:
- **One file per object** under `tests/` (`test_player.py`, `test_group.py`, ...), with a
  single plain test class named `Test<Object>` (`TestPlayer`, `TestGroup`) — pytest's
  default collection convention. No base class is needed.
- **Descriptive method names** that read as behavior, prefixed with `test_`:
  `test_it_detects_what_roles_it_can_fill`, `test_it_correctly_adds_a_player`.
- Call the object under test **`subject`** (e.g. `assert subject.is_full()`).
- Use **plain `assert`** (`assert foo`, `assert a == b`, `assert a < b`) — not
  `self.assertEqual` / `assertTrue` / `assertLess`. Pytest rewrites plain asserts to show
  the compared values, so the helper methods add nothing but noise.
- Don't lean on parametrization — prefer one clearly-named test per behavior so a failure
  name tells you exactly what broke.
- Shared test helpers live in `tests/factories.py` (e.g. `make_player`), imported by the
  per-object test files rather than re-declared in each. A plain importable module (not
  `conftest.py`, which is reserved for pytest fixtures/hooks) keeps the factory explicit
  at each call site.

Run with: `uv run pytest` (config in `pyproject.toml` sets `testpaths` and `pythonpath`,
so no `PYTHONPATH=.` needed).


## Logging

Use logging module. Setup logging in one place, then call the logging setup function.
Don't create individual loggers, just use `logging.info()` and stuff. 
