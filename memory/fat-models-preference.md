---
name: fat-models-preference
description: User prefers fat models — single-object logic lives as methods on the class
metadata:
  type: feedback
---

The user prefers "fat models": business objects (e.g. `Player`, `Group`) should carry
their own logic as methods/properties rather than having free functions that take one
object and only touch its internals.

**Why:** cleaner OO design and easier to write tests later.

**How to apply:** a function like `calculate_group_experience(group)` that only reads
one group's internals belongs on the class as `Group.experience`. Functions operating on
a *collection* (e.g. imbalance across many groups, swap search) can stay as free
functions — they're not single-object logic.
