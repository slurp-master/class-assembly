import random
from typing import List, Dict, Set
from lib.models import Player
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)

GROUP_SIZE = 8
REQUIRED_ROLES = ['tank', 'tank', 'pure', 'shield', 'melee', 'ranged', 'caster', 'flex_dps']
DPS_ROLES = {'melee', 'ranged', 'caster'}


class Group:
    def __init__(self):
        self.members: List[Player] = []
        self.role_slots: List[str] = list(REQUIRED_ROLES)

    def add_member(self, player: Player, role: str) -> bool:
        """Try to add player to group for given role. Returns True if successful."""
        if role not in self.role_slots:
            return False
        self.members.append(player)
        self.role_slots.remove(role)
        return True

    def is_full(self) -> bool:
        return len(self.role_slots) == 0

    def get_needed_roles(self) -> List[str]:
        return self.role_slots

    def ordered_members(self) -> List[Player]:
        sorted_by_name = sorted(self.members, key=lambda p: p.username)
        role_order = ['tank', 'pure', 'shield', 'caster', 'melee', 'ranged']
        role_order = list(reversed(role_order))
        sorted_by_role = sorted(
            sorted_by_name,
            key=lambda p: sum([p.can(r) * (10 ** i) for i, r in enumerate(role_order)]),
            reverse=True,
        )

        return sorted_by_role


class GroupAssembly:
    def __init__(self, players: List[Player], seed: int = None):
        if seed is not None:
            random.seed(seed)
        self.players = players
        self.available = list(players)
        self.groups: List[Group] = []
        self.backup: List[Player] = []
        self.max_groups = self.calculate_max_groups()
        self.dps_role_quota: Dict[str, int] = {}
        self._calculate_dps_quota()

    def calculate_max_groups(self) -> int:
        """Calculate max groups based on tank/healer bottleneck and total players"""
        max_by_total = len(self.players) // GROUP_SIZE

        tanks = sum(1 for p in self.players if 'tank' in p.available_roles)
        pure = sum(1 for p in self.players if 'pure' in p.available_roles)
        shield = sum(1 for p in self.players if 'shield' in p.available_roles)

        max_by_tanks = tanks // 2
        max_by_healers = min(pure, shield)

        return min(max_by_total, max_by_tanks, max_by_healers)

    def _calculate_dps_quota(self):
        """Pre-calculate how many of each DPS type to use per group"""
        dps_counts = {role: sum(1 for p in self.players if role in p.available_roles) for role in DPS_ROLES}

        for role in DPS_ROLES:
            quota = max(0, dps_counts[role] // self.max_groups)
            self.dps_role_quota[role] = quota
            if quota > 0:
                logger.info(f'DPS quota for {role}: {quota} per group')

        self.dps_roles_used: Dict[str, int] = {role: 0 for role in DPS_ROLES}

    def _get_candidates(
        self, needed_role: str, excluded: Set[Player], group_dps_usage: Dict[str, int]
    ) -> List[Player]:
        """Get candidates for a role, sorted by constrainedness then username"""
        candidates = []
        for p in self.available:
            if p in excluded:
                continue

            if needed_role == 'flex_dps':
                if any(role in p.available_roles for role in DPS_ROLES):
                    candidates.append(p)
            elif needed_role in DPS_ROLES:
                if needed_role in p.available_roles:
                    if group_dps_usage.get(needed_role, 0) < self.dps_role_quota.get(
                        needed_role, 0
                    ):
                        candidates.append(p)
            elif needed_role in p.available_roles:
                candidates.append(p)

        candidates.sort(key=lambda p: (p.num_roles, p.username))
        if candidates and len(candidates) > 1:
            min_num_roles = candidates[0].num_roles
            top_candidates = [c for c in candidates if c.num_roles == min_num_roles]
            if len(top_candidates) > 1:
                return random.sample(top_candidates, min(3, len(top_candidates))) + candidates[len(
                    top_candidates
                ):]
        return candidates

    def assemble_groups(self) -> tuple:
        """Greedily assemble groups. Returns (groups, backup)"""
        logger.info(f'Assembling up to {self.max_groups} groups from {len(self.players)} players')

        for group_idx in range(self.max_groups):
            group = Group()
            excluded_this_group = set()
            group_dps_usage = {role: 0 for role in DPS_ROLES}

            while group.get_needed_roles():
                needed_roles = group.get_needed_roles()

                if not needed_roles:
                    break

                selected = None
                selected_role = None

                for needed_role in needed_roles:
                    candidates = self._get_candidates(needed_role, excluded_this_group, group_dps_usage)

                    if candidates:
                        selected = candidates[0]
                        selected_role = needed_role
                        break

                if selected is None:
                    logger.warning(f'Cannot fill group {group_idx}: missing {needed_roles}')
                    break

                group.add_member(selected, selected_role)
                excluded_this_group.add(selected)
                self.available.remove(selected)

                if selected_role in DPS_ROLES:
                    group_dps_usage[selected_role] += 1
                    self.dps_roles_used[selected_role] += 1

            if group.is_full():
                self.groups.append(group)
                logger.info(f'Group {len(self.groups)} formed with {len(group.members)} members')
            else:
                logger.warning(f'Incomplete group {group_idx}: {len(group.members)} members')
                for member in group.members:
                    self.available.add(member)

        self.backup = list(self.available)
        logger.info(f'Final: {len(self.groups)} complete groups, {len(self.backup)} backup')

        return self.groups, self.backup
