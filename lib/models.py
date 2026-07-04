from collections import Counter
from dataclasses import dataclass
from typing import List, Set

GROUP_SIZE = 8
# Fixed non-DPS composition. The remaining 4 slots are DPS (see DPS_ROLES).
FIXED_ROLES = ['tank', 'tank', 'pure', 'shield']
DPS_ROLES = ['melee', 'ranged', 'caster']
DPS_SLOTS = 4


@dataclass(frozen=True)
class Player:
    username: str
    global_name: str
    available_roles: frozenset
    is_backup: bool
    is_raid_leader: bool = False

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
    def __init__(self, needs_raid_leader: bool = False):
        self.assignments: List[Assignment] = []
        # Phantom groups are intentionally formed without a real raid leader, in the
        # hope one is found before the raid starts (setups are made ~a day ahead).
        self.needs_raid_leader = needs_raid_leader

    @property
    def members(self) -> List[Player]:
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

    def dps_flavors(self) -> Set[str]:
        """DPS flavors currently present among assigned roles."""
        return {a.role for a in self.assignments if a.role in DPS_ROLES}

    def is_standard(self) -> bool:
        """True if all three DPS flavors are represented (>=1 each)."""
        return set(DPS_ROLES).issubset(self.dps_flavors())

    def ordered_members(self) -> List[Assignment]:
        """Assignments ordered for readable output: by which roles a player is available
        for (tank, then healers, then DPS), then by name. Uses role *availability*, not
        the tentative assigned role, since the assignment is not surfaced anywhere."""
        priority = ['tank', 'pure', 'shield', 'melee', 'ranged', 'caster']

        def key(a: Assignment):
            p = a.player
            # Higher weight for higher-priority roles the player can fill.
            avail_score = sum(p.can(role) * (10 ** (len(priority) - i)) for i, role in enumerate(priority))
            return (-avail_score, p.username)

        return sorted(self.assignments, key=key)
