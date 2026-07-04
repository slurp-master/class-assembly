import random
from typing import List, Set, Optional
from lib.models import Player, Group, GROUP_SIZE, FIXED_ROLES, DPS_ROLES, DPS_SLOTS
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)


class GroupAssembly:
    def __init__(self, players: List[Player], seed: int = None, phantom_rl: int = 0):
        """Assemble raid groups.

        phantom_rl: number of groups allowed to form *without* a real raid leader, once
        the supply of actual raid leaders is exhausted. These are marked as needing a
        raid leader in the output.
        """
        self.rng = random.Random(seed)
        self.players = players
        self.available: List[Player] = list(players)
        self.groups: List[Group] = []
        self.backup: List[Player] = []
        self.phantom_rl = phantom_rl
        self.non_standard_groups = 0
        self.max_groups = self.calculate_max_groups()

    def calculate_max_groups(self) -> int:
        """Max groups given the tank/healer/raid-leader bottlenecks and total players.

        Every group needs one raid leader, so raid leaders cap the group count just like
        tanks and healers do. Phantom-RL groups extend that cap by ``phantom_rl``.
        """
        max_by_total = len(self.players) // GROUP_SIZE

        tanks = sum(1 for p in self.players if 'tank' in p.available_roles)
        pure = sum(1 for p in self.players if 'pure' in p.available_roles)
        shield = sum(1 for p in self.players if 'shield' in p.available_roles)
        raid_leaders = sum(1 for p in self.players if p.is_raid_leader)

        max_by_tanks = tanks // 2
        max_by_healers = min(pure, shield)
        max_by_rl = raid_leaders + self.phantom_rl

        return min(max_by_total, max_by_tanks, max_by_healers, max_by_rl)

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

    def _available_rl_count(self) -> int:
        return sum(1 for p in self.available if p.is_raid_leader)

    def _candidates_for(self, role: str, excluded: Set[Player], reserved_rl: int) -> List[Player]:
        candidates = [p for p in self.available if p not in excluded and p.can(role)]
        # Reserve raid leaders for the groups that still need one: don't let ordinary
        # role-filling drain the RL pool below what later groups require. If excluding
        # RLs would leave no candidate for this slot, fall back to allowing them.
        if self._available_rl_count() <= reserved_rl:
            non_rl = [p for p in candidates if not p.is_raid_leader]
            if non_rl:
                candidates = non_rl
        # Bench-first: backups only fill slots that no regular signup can cover.
        non_backup = [p for p in candidates if not p.is_backup]
        return non_backup if non_backup else candidates

    def _take(self, group: Group, player: Player, role: str, excluded: Set[Player]):
        group.add(player, role)
        excluded.add(player)
        self.available.remove(player)

    def _fill_role(self, group: Group, role: str, excluded: Set[Player], reserved_rl: int) -> bool:
        """Try to fill one slot of the given role. Returns True on success."""
        chosen = self._pick(self._candidates_for(role, excluded, reserved_rl))
        if chosen is None:
            return False
        self._take(group, chosen, role, excluded)
        return True

    def _seatable_role(self, group: Group, player: Player, roles_left: List[str]) -> Optional[str]:
        """A concrete role from ``roles_left`` this player can fill, or None.

        The ``'dps'`` placeholder matches any DPS flavor the player can play; we return
        the concrete flavor (preferring one still missing from the group, for variety) so
        the caller can record a real role. Fixed roles match directly.
        """
        if any(r == 'dps' for r in roles_left):
            missing = [r for r in DPS_ROLES if r not in group.dps_flavors()]
            for flavor in missing + DPS_ROLES:
                if player.can(flavor):
                    return flavor
        for role in roles_left:
            if role != 'dps' and player.can(role):
                return role
        return None

    def _seat_raid_leader(self, group: Group, roles_left: List[str], excluded: Set[Player]) -> bool:
        """Seat one available raid leader into a composition role they can fill.

        RL-first: this reserves a real raid leader before ordinary members compete for
        slots. We seat the *most constrained* raid leader (fewest playable roles) so an
        inflexible leader isn't stranded once their only viable slot is taken by others.
        A DPS-only leader is placed into a concrete DPS flavor (the ``'dps'`` placeholder
        is resolved). Returns True if a raid leader was seated.
        """
        # Non-backup first (bench-first), then most-constrained; random tie-break (seeded).
        raid_leaders = [p for p in self.available if p.is_raid_leader]
        self.rng.shuffle(raid_leaders)
        raid_leaders.sort(key=lambda p: (p.is_backup, p.num_roles))

        for rl in raid_leaders:
            role = self._seatable_role(group, rl, roles_left)
            if role is not None:
                # Consume one matching slot: the concrete fixed role, or one 'dps'
                # placeholder if the leader took a DPS flavor.
                roles_left.remove(role if role in roles_left else 'dps')
                self._take(group, rl, role, excluded)
                return True
        return False

    def _fill_dps(self, group: Group, roles_left: List[str], excluded: Set[Player], reserved_rl: int) -> bool:
        """Fill the remaining DPS slots in ``roles_left``. Cover all three flavors when
        possible (hard rule when achievable), relaxing to fewer flavors only when no
        strict candidate exists. Returns True if all DPS slots were filled."""
        dps_slots = [r for r in roles_left if r == 'dps']
        for _ in dps_slots:
            missing = [r for r in DPS_ROLES if r not in group.dps_flavors()]
            # Prefer flavors still missing so we cover all three; only relax to any
            # available flavor if none of the missing flavors has a candidate.
            filled = False
            for role in missing + DPS_ROLES:
                if self._fill_role(group, role, excluded, reserved_rl):
                    filled = True
                    break
            if not filled:
                return False
        return True

    def _build_group(self, needs_raid_leader: bool, reserved_rl: int = 0) -> Optional[Group]:
        """Build one complete group, or return None (releasing any partial members).

        reserved_rl: raid leaders that must be left in the pool for later groups, so
        ordinary role-filling in this group won't consume them.
        """
        group = Group(needs_raid_leader=needs_raid_leader)
        excluded: Set[Player] = set()
        # A 'dps' placeholder slot is resolved to a concrete flavor at fill time.
        roles_left: List[str] = list(FIXED_ROLES) + ['dps'] * DPS_SLOTS

        if not needs_raid_leader and not self._seat_raid_leader(group, roles_left, excluded):
            self._release(group)
            return None

        # Fill fixed (non-DPS) roles still outstanding.
        for role in list(roles_left):
            if role == 'dps':
                continue
            if self._fill_role(group, role, excluded, reserved_rl):
                roles_left.remove(role)
            else:
                logger.warning(f'Cannot complete a group: missing {role}')
                self._release(group)
                return None

        if not self._fill_dps(group, roles_left, excluded, reserved_rl):
            logger.warning('Cannot complete a group: not enough DPS')
            self._release(group)
            return None

        return group if group.is_full() else self._release(group)

    def _release(self, group: Group) -> None:
        """Return a failed group's members to the available pool."""
        for player in group.members:
            self.available.append(player)
        return None

    def assemble_groups(self) -> tuple:
        """Greedily assemble groups. Returns (groups, backup)"""
        real_rl = sum(1 for p in self.players if p.is_raid_leader)
        # Groups that will be led by a real raid leader (the rest, if any, are phantom).
        real_rl_groups = min(self.max_groups, real_rl)
        logger.info(
            f'Assembling up to {self.max_groups} groups from {len(self.players)} players '
            f'({real_rl} raid leaders, {self.phantom_rl} phantom allowed)'
        )

        for group_idx in range(self.max_groups):
            # Real raid leaders first; once exhausted, remaining groups are phantom.
            needs_raid_leader = not any(p.is_raid_leader for p in self.available)
            # Reserve one RL for each real-RL group still to be built after this one.
            reserved_rl = max(0, real_rl_groups - (group_idx + 1))
            group = self._build_group(needs_raid_leader, reserved_rl=reserved_rl)

            if group is None:
                logger.warning(f'Incomplete group {group_idx + 1}, releasing members')
                continue

            self.groups.append(group)
            if not group.is_standard():
                self.non_standard_groups += 1
                logger.warning(
                    f'Group {len(self.groups)} has non-standard DPS composition '
                    f'(flavors: {sorted(group.dps_flavors())}) -- raid is viable but harder'
                )
            if group.needs_raid_leader:
                logger.warning(f'Group {len(self.groups)} formed WITHOUT a raid leader (phantom)')
            logger.info(f'Group {len(self.groups)} formed with {len(group.members)} members')

        self.backup = list(self.available)
        phantom = sum(1 for g in self.groups if g.needs_raid_leader)
        logger.info(
            f'Final: {len(self.groups)} complete groups '
            f'({self.non_standard_groups} non-standard, {phantom} phantom-RL), '
            f'{len(self.backup)} backup'
        )

        return self.groups, self.backup
