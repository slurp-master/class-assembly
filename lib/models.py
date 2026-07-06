from collections import Counter
from dataclasses import dataclass

GROUP_SIZE = 8
# Fixed non-DPS composition. The remaining 4 slots are DPS (see DPS_ROLES).
FIXED_ROLES = ['tank', 'tank', 'pure', 'shield']
DPS_ROLES = ['melee', 'ranged', 'caster']
DPS_SLOTS = 4
_STANDARD_SLOTS = FIXED_ROLES + DPS_ROLES + ['dps']

# Placeholder names cycled across phantom-RL groups (drawn from the pool in order).
PHANTOM_RL_NAMES = ['Raidingway', 'Teachingway', 'Wipingway']


@dataclass(frozen=True)
class Player:
    username: str
    global_name: str
    available_roles: frozenset
    is_backup: bool
    is_raid_leader: bool = False

    @property
    def is_phantom_rl(self) -> bool:
        """True if this player is a placeholder for a phantom raid leader slot."""
        return self.global_name in PHANTOM_RL_NAMES

    @property
    def num_roles(self) -> int:
        """Number of roles this player can fill (used for constrainedness)"""
        return len(self.available_roles)

    @property
    def experience(self) -> int:
        """Numeric experience for this player.

        Real experience indicators are not wired up yet; for now we use the number of
        roles a player signed up for as a proxy (more flexible players tend to be more
        experienced). This property is the single place experience is produced -- swapping
        in a real source later only touches here. Nothing else should read ``num_roles``
        for balancing purposes.
        """
        return self.num_roles

    def can(self, role: str) -> bool:
        return role in self.available_roles

    def __lt__(self, other):
        """Define ordering for deterministic sorting"""
        return self.username < other.username


@dataclass(frozen=True)
class Assignment:
    """A player placed into a group for a specific role."""
    player: Player
    role: str

    @property
    def experience(self) -> int:
        return self.player.experience

    def can_swap_with(self, other: 'Assignment') -> bool:
        """A swap keeps both groups' compositions valid iff each player can play the
        other's assigned role -- this assignment takes ``other``'s role slot and vice
        versa."""
        return self.player.can(other.role) and other.player.can(self.role)


class Group:
    def __init__(self):
        self.assignments: list[Assignment] = []

    @property
    def needs_raid_leader(self) -> bool:
        """True if this group has a placeholder RL — a real leader still needs to be found."""
        return any(p.is_phantom_rl for p in self.members)

    @property
    def members(self) -> list[Player]:
        return [a.player for a in self.assignments]

    @property
    def experience(self) -> int:
        """Total experience of the group (sum of member experiences)."""
        return sum(a.experience for a in self.assignments)

    @property
    def raid_leader_count(self) -> int:
        return sum(1 for a in self.assignments if a.player.is_raid_leader)

    @property
    def has_raid_leader(self) -> bool:
        return self.raid_leader_count > 0

    @property
    def required_raid_leaders(self) -> int:
        """Minimum raid leaders this group must keep. Phantom groups require none."""
        return 0 if self.needs_raid_leader else 1

    def swap_keeps_raid_leader(self, mine: Assignment, incoming: Player) -> bool:
        """Would swapping out ``mine`` for ``incoming`` still satisfy this group's raid
        leader requirement?"""
        count = self.raid_leader_count - mine.player.is_raid_leader + incoming.is_raid_leader
        return count >= self.required_raid_leaders

    def add(self, player: Player, role: str):
        self.assignments.append(Assignment(player=player, role=role))

    def swap(self, mine: Assignment, other: 'Group', theirs: Assignment):
        """Swap two players between this group and ``other``, each taking over the
        other's role slot. Caller is responsible for checking ``mine.can_swap_with``."""
        self.assignments.remove(mine)
        other.assignments.remove(theirs)
        self.assignments.append(Assignment(player=theirs.player, role=mine.role))
        other.assignments.append(Assignment(player=mine.player, role=theirs.role))

    def role_counts(self) -> Counter:
        """How many assignments this group holds per role."""
        return Counter(a.role for a in self.assignments)

    def has_valid_composition(self) -> bool:
        """True if the assigned roles match the fixed composition: the exact tank/pure/
        shield counts plus DPS_SLOTS DPS across the three flavors.

        Count alone is not enough -- eight tanks fills every seat but is not a raid group.
        This is the trustworthy 'is this a real, complete group' check.
        """
        counts = self.role_counts()
        fixed_needed = Counter(FIXED_ROLES)
        if any(counts.get(role, 0) != n for role, n in fixed_needed.items()):
            return False
        dps = sum(counts.get(flavor, 0) for flavor in DPS_ROLES)
        # Any leftover roles outside the fixed set and DPS flavors make it invalid.
        known = set(fixed_needed) | set(DPS_ROLES)
        if any(role not in known for role in counts):
            return False
        return dps == DPS_SLOTS

    def is_full(self) -> bool:
        """A group is complete only when its seats are filled *and* the composition is
        valid -- a count of eight with the wrong roles is not a full group."""
        return len(self.assignments) == GROUP_SIZE and self.has_valid_composition()

    def dps_flavors(self) -> set[str]:
        """DPS flavors currently present among assigned roles."""
        return {a.role for a in self.assignments if a.role in DPS_ROLES}

    def is_standard(self) -> bool:
        """True if all three DPS flavors are represented (>=1 each)."""
        return set(DPS_ROLES).issubset(self.dps_flavors())

    def repair_composition(self) -> bool:
        """Try to reassign roles so all three DPS flavors are covered.

        Only roles change — the set of players stays the same. Returns True if the group
        is standard after the call (either it already was, or the repair succeeded).

        Uses backtracking over _STANDARD_SLOTS (2×tank, pure, shield, melee, ranged,
        caster, any-DPS). The three named DPS slots come before the wildcard, so flavor
        coverage is maximised before the free slot is resolved. A fixed-role player (e.g.
        a shield/caster player greedily assigned to shield) can be reassigned to DPS if
        another player can cover their fixed slot instead.
        """
        if self.is_standard():
            return True

        assignment: list[tuple['Player', str]] = []

        def backtrack(slot_idx: int, remaining: list['Player']) -> bool:
            if slot_idx == len(_STANDARD_SLOTS):
                return True
            slot = _STANDARD_SLOTS[slot_idx]
            for i, player in enumerate(remaining):
                can_fill = any(player.can(f) for f in DPS_ROLES) if slot == 'dps' else player.can(slot)
                if not can_fill:
                    continue
                role = slot if slot != 'dps' else next(f for f in DPS_ROLES if player.can(f))
                assignment.append((player, role))
                if backtrack(slot_idx + 1, remaining[:i] + remaining[i + 1:]):
                    return True
                assignment.pop()
            return False

        if not backtrack(0, self.members):
            return False
        self.assignments = [Assignment(player=p, role=r) for p, r in assignment]
        return True

    def ordered_members(self) -> list[Assignment]:
        """Assignments ordered for readable output: by which roles a player is available
        for (tank, then healers, then DPS), then by name. Uses role *availability*, not
        the tentative assigned role, since the assignment is not surfaced anywhere."""
        priority = ['tank', 'pure', 'shield', 'melee', 'ranged', 'caster']

        def key(a: Assignment):
            p = a.player
            # Higher weight for higher-priority roles the player can fill.
            avail_score = sum(p.can(role) * (10 ** (len(priority) - i)) for i, role in enumerate(priority))
            return (not p.is_raid_leader, -avail_score, p.username)

        return sorted(self.assignments, key=key)
