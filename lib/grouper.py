import random
from lib.models import Player, Group, GROUP_SIZE, FIXED_ROLES, DPS_ROLES, DPS_SLOTS
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)


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
        the supply of actual raid leaders is exhausted. These are marked as needing a
        raid leader in the output.

        pairs: bidirectional {global_name -> partner_global_name} lookup produced by
        lib.pairs.build_pair_lookup. Paired players whose partner is still available are
        preferred during candidate selection, giving them a better chance of landing in
        the same group. The constraint is best-effort: pairs never block group formation.
        """
        self._rng = random.Random(seed)
        self._players = players
        self._available: list[Player] = list(players)
        self._groups: list[Group] = []
        self._backup: list[Player] = []
        self._phantom_rl = phantom_rl
        self._pairs: dict[str, str] = pairs or {}
        self._violated_pairs: list[tuple[str, str]] = []
        self._non_standard_groups = 0
        self._max_groups = self._calculate_max_groups()

    def _calculate_max_groups(self) -> int:
        """Max groups given the tank/healer/raid-leader bottlenecks and total players.

        Every group needs one raid leader, so raid leaders cap the group count just like
        tanks and healers do. Phantom-RL groups extend that cap by ``_phantom_rl``.
        """
        max_by_total = len(self._players) // GROUP_SIZE

        tanks = sum(1 for p in self._players if 'tank' in p.available_roles)
        pure = sum(1 for p in self._players if 'pure' in p.available_roles)
        shield = sum(1 for p in self._players if 'shield' in p.available_roles)
        raid_leaders = sum(1 for p in self._players if p.is_raid_leader)

        max_by_tanks = tanks // 2
        max_by_healers = min(pure, shield)
        max_by_rl = raid_leaders + self._phantom_rl

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

        keyed = sorted((priority(p), p) for p in candidates)
        best = keyed[0][0]
        top = [p for key, p in keyed if key == best]
        return self._rng.choice(top)

    def _available_rl_count(self) -> int:
        return sum(1 for p in self._available if p.is_raid_leader)

    def _candidates_for(
        self, role: str, excluded: set[Player], reserved_rl: int, group: Group = None
    ) -> list[Player]:
        candidates = [p for p in self._available if p not in excluded and p.can(role)]
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

    def _fill_role(self, group: Group, role: str, excluded: set[Player], reserved_rl: int) -> bool:
        """Try to fill one slot of the given role. Returns True on success."""
        chosen = self._pick(self._candidates_for(role, excluded, reserved_rl, group=group), group=group)
        if chosen is None:
            return False
        self._take(group, chosen, role, excluded)
        return True

    def _seatable_role(self, group: Group, player: Player, roles_left: list[str]) -> str | None:
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

    def _seat_raid_leader(self, group: Group, roles_left: list[str], excluded: set[Player]) -> bool:
        """Seat one available raid leader into a composition role they can fill.

        RL-first: this reserves a real raid leader before ordinary members compete for
        slots. We seat the *most constrained* raid leader (fewest playable roles) so an
        inflexible leader isn't stranded once their only viable slot is taken by others.
        A DPS-only leader is placed into a concrete DPS flavor (the ``'dps'`` placeholder
        is resolved). Returns True if a raid leader was seated.
        """
        # Non-backup first (bench-first), then most-constrained; random tie-break (seeded).
        raid_leaders = [p for p in self._available if p.is_raid_leader]
        self._rng.shuffle(raid_leaders)
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

    def _fill_dps(self, group: Group, roles_left: list[str], excluded: set[Player], reserved_rl: int) -> bool:
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

    def _build_group(self, needs_raid_leader: bool, reserved_rl: int = 0) -> Group | None:
        """Build one complete group, or return None (releasing any partial members).

        reserved_rl: raid leaders that must be left in the pool for later groups, so
        ordinary role-filling in this group won't consume them.
        """
        group = Group(needs_raid_leader=needs_raid_leader)
        excluded: set[Player] = set()
        # A 'dps' placeholder slot is resolved to a concrete flavor at fill time.
        roles_left: list[str] = list(FIXED_ROLES) + ['dps'] * DPS_SLOTS

        if not needs_raid_leader and not self._seat_raid_leader(group, roles_left, excluded):
            self._release(group)
            return None

        # Fill fixed (non-DPS) roles still outstanding.
        for role in list(roles_left):
            if role == 'dps':
                continue
            if not self._fill_role(group, role, excluded, reserved_rl):
                logger.warning(f'Cannot complete a group: missing {role}')
                self._release(group)
                return None
            roles_left.remove(role)

        if not self._fill_dps(group, roles_left, excluded, reserved_rl):
            logger.warning('Cannot complete a group: not enough DPS')
            self._release(group)
            return None

        return group if group.is_full() else self._release(group)

    def _release(self, group: Group) -> None:
        """Return a failed group's members to the available pool."""
        for player in group.members:
            self._available.append(player)
        return None

    def assemble_groups(self) -> tuple[list[Group], list[Player], list[tuple[str, str]]]:
        """Greedily assemble groups. Returns (groups, backup, violated_pairs)."""
        real_rl = sum(1 for p in self._players if p.is_raid_leader)
        # Groups that will be led by a real raid leader (the rest, if any, are phantom).
        real_rl_groups = min(self._max_groups, real_rl)
        logger.info(
            f'Assembling up to {self._max_groups} groups from {len(self._players)} players '
            f'({real_rl} raid leaders, {self._phantom_rl} phantom allowed)'
        )

        for group_idx in range(self._max_groups):
            # Real raid leaders first; once exhausted, remaining groups are phantom.
            needs_raid_leader = not any(p.is_raid_leader for p in self._available)
            # Reserve one RL for each real-RL group still to be built after this one.
            reserved_rl = max(0, real_rl_groups - (group_idx + 1))
            group = self._build_group(needs_raid_leader, reserved_rl=reserved_rl)

            if group is None:
                logger.warning(f'Incomplete group {group_idx + 1}, releasing members')
                continue

            self._groups.append(group)
            if not group.is_standard():
                self._non_standard_groups += 1
                logger.warning(
                    f'Group {len(self._groups)} has non-standard DPS composition '
                    f'(flavors: {sorted(group.dps_flavors())}) -- raid is viable but harder'
                )
            if group.needs_raid_leader:
                logger.warning(f'Group {len(self._groups)} formed WITHOUT a raid leader (phantom)')
            logger.info(f'Group {len(self._groups)} formed with {len(group.members)} members')

        self._backup = list(self._available)
        phantom = sum(1 for g in self._groups if g.needs_raid_leader)
        logger.info(
            f'Final: {len(self._groups)} complete groups '
            f'({self._non_standard_groups} non-standard, {phantom} phantom-RL), '
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
