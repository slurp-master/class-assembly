# Project: Raid group setup creation

Automation for an MMO-RPG raiding community. Members sign up for events by reacting
to a Discord message (one reaction per role they are comfortable with). The tool takes
those signups and combines people into balanced raid groups that satisfy a fixed role
composition, so an organizer doesn't have to do it by hand.

## Pipeline

1. `010_parse_reactions.py` — parses the per-role Discord reaction JSON exports
   (`data/<event>/*.json`) into a single `data/010_reactions/reactions.csv`. Each row is
   a player; boolean columns mark which roles they signed up for plus `backup`.
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
- **Maximize the number of complete groups.** Players who don't fit go to the bench;
  players who opted into `backup` are the natural bench candidates.

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

## Approach

Greedy constructor + swap-based local search. No need for a provably optimal solution;
"good enough" that a human can eyeball and hand-tweak is the goal. Being able to re-run
with different seeds to get alternative setups is valuable — the initial solve is the
time-consuming part, not evaluating a candidate.

## Output

- `data/020_setup/setup.csv` — canonical, machine-readable; imported into other systems.
  Columns: `group_id`, `global_name`, then a boolean per role (role availability, not an
  assignment). Bench players get `group_id = backup`.
- Console table — human-readable preview for the operator to sanity-check a run. Same
  data, `✓` marks, emojis stripped from names for terminal legibility.

Keep **both**; they serve different consumers. Neither shows an assigned role.

## Scope

In scope: role composition + experience balancing. **Deferred** (mentioned but not yet
built): "pairs" (people who want to be grouped together) and any signup/user-experience
work.


## Code style
Use single quotes in code.
Line length limit: 120.

**Fat models.** Business objects (`Player`, `Group`, `Assignment`) own their logic. Any
function that takes a single object and only touches its internals belongs on the class
as a method/property (e.g. `Group.experience`, `Assignment.can_swap_with`). Functions
operating over a *collection* of objects (e.g. imbalance across all groups, the swap
search) stay as free functions. This keeps logic discoverable and eases unit testing.


## Logging

Use logging module. Setup logging in one place, then call the logging setup function.
Don't create individual loggers, just use `logging.info()` and stuff. 
