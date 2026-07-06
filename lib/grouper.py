import random
from lib.models import Player, Group, GROUP_SIZE, FIXED_ROLES, DPS_ROLES, DPS_SLOTS, PHANTOM_RL_NAMES
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)

_ALL_ROLES = frozenset(FIXED_ROLES) | frozenset(DPS_ROLES)


def _can_fill_slot(player: Player, slot: str) -> bool:
    """True if ``player`` can fill ``slot``.

    ``'dps'`` matches any DPS flavor; all other slots are a direct role lookup.
    """
    return any(player.can(f) for f in DPS_ROLES) if slot == 'dps' else player.can(slot)


def _make_phantoms(count: int) -> list[Player]:
    """Create ``count`` placeholder RL players, cycling through PHANTOM_RL_NAMES."""
    names = [PHANTOM_RL_NAMES[i % len(PHANTOM_RL_NAMES)] for i in range(count)]
    return [
        Player(
            username=name.lower(),
            global_name=name,
            available_roles=_ALL_ROLES,
            is_backup=False,
            is_raid_leader=True,
        )
        for name in names
    ]


class GroupAssembly:
    def __init__(
        self,
        players: list[Player],
        seed: int = None,
        phantom_rl: int = 0,
        pairs: dict[str, str] = None,
    ):
        """Assemble raid groups.

        phantom_rl: number of groups allowed to form *without* a real raid leader, once
        the supply of actual raid leaders is exhausted. Placeholder players (drawn from
        PHANTOM_RL_NAMES) are pre-seeded into the available pool and go through the same
        RL-first seating path as real leaders; their groups are flagged as needing a real
        raid leader in the output.

        pairs: bidirectional {global_name -> partner_global_name} lookup produced by
        lib.pairs.build_pair_lookup. Paired players whose partner is still available are
        preferred during candidate selection, giving them a better chance of landing in
        the same group. The constraint is best-effort: pairs never block group formation.
        """
        self._rng = random.Random(seed)
        self._real_players = players
        phantoms = _make_phantoms(phantom_rl)
        # Phantoms are appended after real players so real RLs are exhausted first.
        self._available: list[Player] = list(players) + phantoms
        self._groups: list[Group] = []
        self._backup: list[Player] = []
        self._pairs: dict[str, str] = pairs or {}
        self._violated_pairs: list[tuple[str, str]] = []
        self._max_groups = self._calculate_max_groups()

    def _calculate_max_groups(self) -> int:
        """Max groups given the tank/healer/raid-leader bottlenecks and total pool size.

        Phantoms are already in the pool, so max_by_total naturally accounts for them
        consuming one slot each (GROUP_SIZE players per group, phantoms included).
        """
        pool = self._available
        max_by_total = len(pool) // GROUP_SIZE

        tanks = sum(1 for p in pool if 'tank' in p.available_roles)
        pure = sum(1 for p in pool if 'pure' in p.available_roles)
        shield = sum(1 for p in pool if 'shield' in p.available_roles)
        raid_leaders = sum(1 for p in pool if p.is_raid_leader)

        max_by_tanks = tanks // 2
        max_by_healers = min(pure, shield)
        max_by_rl = raid_leaders  # includes phantoms

        return min(max_by_total, max_by_tanks, max_by_healers, max_by_rl)

    def _partner_in_group(self, player: Player, group: Group) -> bool:
        """True if this player's pair partner is already seated in ``group``."""
        partner_name = self._pairs.get(player.global_name)
        if partner_name is None:
            return False
        return any(p.global_name == partner_name for p in group.members)

    def _has_available_partner(self, player: Player) -> bool:
        """True if this player has a pair and their partner is still in the available pool."""
        partner_name = self._pairs.get(player.global_name)
        if partner_name is None:
            return False
        return any(p.global_name == partner_name for p in self._available)

    def _pick(self, candidates: list[Player], group: Group = None) -> Player | None:
        """Pick the best candidate using a three-level priority:
        1. Partner already seated in this group (complete the pair now).
        2. Partner still available (seat paired players early so their partner can follow).
        3. Most constrained (fewest roles) within each tier.
        4. Random tie-break among the top candidates (seeded for reproducibility).
        """
        if not candidates:
            return None

        def priority(p: Player) -> tuple:
            partner_here = group is not None and self._partner_in_group(p, group)
            partner_available = self._has_available_partner(p)
            # Lower value = higher priority.
            return (not partner_here, not partner_available, p.num_roles, p.username)

        best = min(priority(p) for p in candidates)
        top = [p for p in candidates if priority(p) == best]
        return self._rng.choice(top)

    def _available_rl_count(self) -> int:
        """Count of real (non-phantom) raid leaders still in the pool.

        Used by the reservation guard to prevent ordinary role-filling from draining real
        RLs below what later real-RL groups need. Phantoms are excluded because they are
        never reserved for real-RL groups.
        """
        return sum(1 for p in self._available if p.is_raid_leader and not p.is_phantom_rl)

    def _candidates_for(
        self, slot: str, excluded: set[Player], reserved_rl: int, group: Group = None
    ) -> list[Player]:
        candidates = [p for p in self._available if p not in excluded and _can_fill_slot(p, slot)]
        # Reserve raid leaders for the groups that still need one: don't let ordinary
        # role-filling drain the RL pool below what later groups require. If excluding
        # RLs would leave no candidate for this slot, fall back to allowing them.
        if self._available_rl_count() <= reserved_rl:
            non_rl = [p for p in candidates if not p.is_raid_leader]
            if non_rl:
                candidates = non_rl
        # Bench-first: backups only fill slots that no regular signup can cover —
        # except when a backup's pair partner is already in this group, in which case
        # the social constraint outweighs bench-first.
        non_backup = [p for p in candidates if not p.is_backup]
        if non_backup:
            paired_backups = [
                p for p in candidates
                if p.is_backup and group is not None and self._partner_in_group(p, group)
            ]
            return non_backup + paired_backups
        return candidates

    def _take(self, group: Group, player: Player, role: str, excluded: set[Player]):
        group.add(player, role)
        excluded.add(player)
        self._available.remove(player)

    def _fill_slot(self, group: Group, slot: str, excluded: set[Player], reserved_rl: int) -> bool:
        """Fill one slot (fixed role or ``'dps'``). Returns True on success.

        For ``'dps'`` slots the concrete flavor is resolved at fill time, preferring
        flavors not yet present in the group.
        """
        chosen = self._pick(self._candidates_for(slot, excluded, reserved_rl, group=group), group=group)
        if chosen is None:
            return False
        role = self._resolve_dps_flavor(group, chosen) if slot == 'dps' else slot
        self._take(group, chosen, role, excluded)
        return True

    def _seatable_slot(self, group: Group, player: Player, roles_left: list[str]) -> str | None:
        """The first slot in ``roles_left`` this player can fill, or None.

        Returns the slot name as stored — ``'dps'`` if the player can fill any DPS flavor,
        or the concrete fixed role name. Callers use ``_resolve_dps_flavor`` to get the
        concrete flavor when the returned slot is ``'dps'``.
        """
        for slot in roles_left:
            if _can_fill_slot(player, slot):
                return slot
        return None

    def _resolve_dps_flavor(self, group: Group, player: Player) -> str:
        """Concrete DPS flavor for a player filling a ``'dps'`` slot.

        Prefers flavors not yet present in the group for variety; falls back to any flavor
        the player can fill. Assumes the player can fill at least one DPS flavor.
        """
        missing = [f for f in DPS_ROLES if f not in group.dps_flavors()]
        for flavor in missing + DPS_ROLES:
            if player.can(flavor):
                return flavor

    def _seat_raid_leader(
        self, group: Group, roles_left: list[str], excluded: set[Player]
    ) -> Player | None:
        """Seat one available raid leader into a composition role they can fill.

        RL-first: this reserves a real raid leader before ordinary members compete for
        slots. We seat the *most constrained* raid leader (fewest playable roles) so an
        inflexible leader isn't stranded once their only viable slot is taken by others.
        A DPS-only leader is placed into a concrete DPS flavor (the ``'dps'`` placeholder
        is resolved). Returns the seated Player, or None if no raid leader could be seated.
        """
        # Real RLs first (phantoms are last resort), then non-backup, then most-constrained.
        raid_leaders = [p for p in self._available if p.is_raid_leader]
        self._rng.shuffle(raid_leaders)
        raid_leaders.sort(key=lambda p: (p.is_phantom_rl, p.is_backup, p.num_roles))

        for rl in raid_leaders:
            slot = self._seatable_slot(group, rl, roles_left)
            if slot is not None:
                role = self._resolve_dps_flavor(group, rl) if slot == 'dps' else slot
                roles_left.remove(slot)
                self._take(group, rl, role, excluded)
                return rl
        return None

    def _build_group(self, reserved_rl: int = 0) -> Group | None:
        """Build one complete group, or return None (releasing any partial members).

        reserved_rl: raid leaders that must be left in the pool for later groups, so
        ordinary role-filling in this group won't consume them.
        """
        group = Group()
        excluded: set[Player] = set()
        slots: list[str] = list(FIXED_ROLES) + ['dps'] * DPS_SLOTS

        if self._seat_raid_leader(group, slots, excluded) is None:
            self._release(group)
            return None

        for slot in slots:
            if not self._fill_slot(group, slot, excluded, reserved_rl):
                logger.warning(f'Cannot complete a group: missing {slot}')
                self._release(group)
                return None

        if not group.is_full():
            return self._release(group)
        group.repair_composition()
        return group

    def _release(self, group: Group) -> None:
        """Return a failed group's members to the available pool."""
        for player in group.members:
            self._available.append(player)
        return None

    def assemble_groups(self) -> tuple[list[Group], list[Player], list[tuple[str, str]]]:
        """Greedily assemble groups. Returns (groups, backup, violated_pairs)."""
        real_rl = sum(1 for p in self._real_players if p.is_raid_leader)
        # Groups that will be led by a real raid leader (the rest, if any, are phantom).
        real_rl_groups = min(self._max_groups, real_rl)
        logger.info(
            f'Assembling up to {self._max_groups} groups from {len(self._real_players)} players '
            f'({real_rl} raid leaders, {self._max_groups - real_rl_groups} phantom allowed)'
        )

        for group_idx in range(self._max_groups):
            # Reserve one RL for each real-RL group still to be built after this one.
            reserved_rl = max(0, real_rl_groups - (group_idx + 1))
            group = self._build_group(reserved_rl=reserved_rl)

            if group is None:
                logger.warning(f'Incomplete group {group_idx + 1}, releasing members')
                continue

            self._groups.append(group)
            if group.needs_raid_leader:
                logger.warning(f'Group {len(self._groups)} formed WITHOUT a raid leader (phantom)')
            logger.info(f'Group {len(self._groups)} formed with {len(group.members)} members')

        # Bench is whatever real players remain; phantoms are discarded.
        self._backup = [p for p in self._available if not p.is_phantom_rl]
        phantom = sum(1 for g in self._groups if g.needs_raid_leader)
        logger.info(
            f'Final: {len(self._groups)} complete groups '
            f'({phantom} phantom-RL), '
            f'{len(self._backup)} backup'
        )

        self._detect_violated_pairs()

        return self._groups, self._backup, self._violated_pairs

    def _detect_violated_pairs(self):
        """Record all active pairs where the two members ended up in different groups (or
        one/both on the bench). Each canonical pair appears at most once.
        """
        placement: dict[str, int | None] = {}
        for idx, group in enumerate(self._groups):
            for p in group.members:
                if not p.is_phantom_rl:
                    placement[p.global_name] = idx
        for p in self._backup:
            placement[p.global_name] = None

        seen: set = set()
        for name, partner_name in self._pairs.items():
            canonical = tuple(sorted((name, partner_name)))
            if canonical in seen:
                continue
            seen.add(canonical)
            group_a = placement.get(name)
            group_b = placement.get(partner_name)
            if group_a != group_b or group_a is None:
                self._violated_pairs.append(canonical)
