import random
from typing import List, Dict, Set, Optional
from lib.models import Player, Assignment
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)

GROUP_SIZE = 8
# Fixed non-DPS composition. The remaining 4 slots are DPS (see DPS_ROLES).
FIXED_ROLES = ['tank', 'tank', 'pure', 'shield']
DPS_ROLES = ['melee', 'ranged', 'caster']
DPS_SLOTS = 4


class Group:
    def __init__(self):
        self.assignments: List[Assignment] = []

    @property
    def members(self) -> List[Player]:
        return [a.player for a in self.assignments]

    @property
    def experience(self) -> int:
        """Total experience of the group (sum of member experiences)."""
        return sum(a.experience for a in self.assignments)

    def add(self, player: Player, role: str):
        self.assignments.append(Assignment(player=player, role=role))

    def swap(self, mine: Assignment, other: 'Group', theirs: Assignment):
        """Swap two players between this group and ``other``, each taking over the
        other's role slot. Caller is responsible for checking ``mine.can_swap_with``."""
        self.assignments.remove(mine)
        other.assignments.remove(theirs)
        self.assignments.append(Assignment(player=theirs.player, role=mine.role))
        other.assignments.append(Assignment(player=mine.player, role=theirs.role))

    def is_full(self) -> bool:
        return len(self.assignments) == GROUP_SIZE

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


class GroupAssembly:
    def __init__(self, players: List[Player], seed: int = None):
        self.rng = random.Random(seed)
        self.players = players
        self.available: List[Player] = list(players)
        self.groups: List[Group] = []
        self.backup: List[Player] = []
        self.max_groups = self.calculate_max_groups()
        self.non_standard_groups = 0

    def calculate_max_groups(self) -> int:
        """Calculate max groups based on tank/healer bottleneck and total players"""
        max_by_total = len(self.players) // GROUP_SIZE

        tanks = sum(1 for p in self.players if 'tank' in p.available_roles)
        pure = sum(1 for p in self.players if 'pure' in p.available_roles)
        shield = sum(1 for p in self.players if 'shield' in p.available_roles)

        max_by_tanks = tanks // 2
        max_by_healers = min(pure, shield)

        return min(max_by_total, max_by_tanks, max_by_healers)

    def _pick(self, candidates: List[Player]) -> Optional[Player]:
        """Pick the most constrained candidate (fewest roles), breaking near-ties randomly.

        Sorting hardest-to-place first keeps flexible players available for later slots.
        Among the most-constrained candidates we sample randomly so different seeds
        yield different-but-valid setups.
        """
        if not candidates:
            return None
        candidates = sorted(candidates, key=lambda p: (p.num_roles, p.username))
        min_num_roles = candidates[0].num_roles
        top = [c for c in candidates if c.num_roles == min_num_roles]
        return self.rng.choice(top)

    def _candidates_for(self, role: str, excluded: Set[Player]) -> List[Player]:
        return [p for p in self.available if p not in excluded and p.can(role)]

    def _fill_role(self, group: Group, role: str, excluded: Set[Player]) -> bool:
        """Try to fill one slot of the given role. Returns True on success."""
        chosen = self._pick(self._candidates_for(role, excluded))
        if chosen is None:
            return False
        group.add(chosen, role)
        excluded.add(chosen)
        self.available.remove(chosen)
        return True

    def _fill_dps(self, group: Group, excluded: Set[Player]) -> bool:
        """Fill the 4 DPS slots. Cover all three flavors when possible (hard rule when
        achievable), relaxing to fewer flavors only when no strict candidate exists.
        Returns True if all 4 slots were filled."""
        for _ in range(DPS_SLOTS):
            missing = [r for r in DPS_ROLES if r not in group.dps_flavors()]
            # Prefer flavors still missing so we cover all three; only if none of the
            # missing flavors has a candidate do we relax to any available flavor.
            filled = False
            for role in missing:
                if self._fill_role(group, role, excluded):
                    filled = True
                    break
            if not filled:
                # Relax: take any DPS flavor still available.
                for role in DPS_ROLES:
                    if self._fill_role(group, role, excluded):
                        filled = True
                        break
            if not filled:
                return False
        return True

    def assemble_groups(self) -> tuple:
        """Greedily assemble groups. Returns (groups, backup)"""
        logger.info(f'Assembling up to {self.max_groups} groups from {len(self.players)} players')

        for group_idx in range(self.max_groups):
            group = Group()
            excluded: Set[Player] = set()

            ok = True
            for role in FIXED_ROLES:
                if not self._fill_role(group, role, excluded):
                    logger.warning(f'Cannot fill group {group_idx + 1}: missing {role}')
                    ok = False
                    break

            if ok and not self._fill_dps(group, excluded):
                logger.warning(f'Cannot fill group {group_idx + 1}: not enough DPS')
                ok = False

            if ok and group.is_full():
                self.groups.append(group)
                if not group.is_standard():
                    self.non_standard_groups += 1
                    logger.warning(
                        f'Group {len(self.groups)} has non-standard DPS composition '
                        f'(flavors: {sorted(group.dps_flavors())}) -- raid is viable but harder'
                    )
                logger.info(f'Group {len(self.groups)} formed with {len(group.members)} members')
            else:
                # Return this group's members to the pool for later groups / backup.
                logger.warning(f'Incomplete group {group_idx + 1}: {len(group.members)} members, releasing')
                for player in group.members:
                    self.available.append(player)

        self.backup = list(self.available)
        logger.info(
            f'Final: {len(self.groups)} complete groups '
            f'({self.non_standard_groups} non-standard), {len(self.backup)} backup'
        )

        return self.groups, self.backup
