from lib.models import GROUP_SIZE, DPS_ROLES
from lib.grouper import GroupAssembly
from lib.balancer import swap_members_for_balance
from tests.factories import make_player

ALL_ROLES = ('tank', 'pure', 'shield', 'melee', 'ranged', 'caster')


def player(username, roles=ALL_ROLES, is_raid_leader=False, is_backup=False):
    """An omni-role player by default -- most assembly tests want players who can fill
    any slot so role scarcity is controlled explicitly per test."""
    return make_player(username, roles=roles, is_backup=is_backup, is_raid_leader=is_raid_leader)


def omni_roster(count, raid_leaders):
    """`count` players who can play every role; the first `raid_leaders` of them are RLs."""
    return [
        player(f'p{i}', roles=ALL_ROLES, is_raid_leader=(i < raid_leaders))
        for i in range(count)
    ]


def assemble(players, seed=0, phantom_rl=0, pairs=None):
    return GroupAssembly(players, seed=seed, phantom_rl=phantom_rl, pairs=pairs or {}).assemble_groups()


def assert_valid_composition(group):
    """Every formed group must be full and hold exactly 2 tank, 1 pure, 1 shield, 4 DPS
    by tentative role."""
    roles = [a.role for a in group.assignments]
    assert group.is_full()
    assert roles.count('tank') == 2
    assert roles.count('pure') == 1
    assert roles.count('shield') == 1
    assert sum(1 for r in roles if r in DPS_ROLES) == 4


def assert_no_player_used_twice(groups, backup, players):
    seen = [p.username for g in groups for p in g.members] + [p.username for p in backup]
    assert len(seen) == len(set(seen))          # nobody in two places
    assert set(seen) == {p.username for p in players}  # nobody lost


class TestGroupAssembly:
    # --- generous role presence: how many groups form at various sizes ---

    def test_it_forms_a_single_group_from_a_generous_small_roster(self):
        players = omni_roster(count=11, raid_leaders=2)  # 8 needed, 3 spare -> backup
        groups, backup, _ = assemble(players)
        assert len(groups) == 1
        assert len(backup) == 3
        assert_valid_composition(groups[0])
        assert_no_player_used_twice(groups, backup, players)

    def test_it_forms_multiple_groups_from_a_generous_roster(self):
        players = omni_roster(count=27, raid_leaders=5)  # 3 full groups (24) + 3 backup
        groups, backup, _ = assemble(players)
        assert len(groups) == 3
        assert len(backup) == 3
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    def test_it_forms_up_to_five_groups_when_the_roster_is_large(self):
        players = omni_roster(count=45, raid_leaders=8)  # 5 full groups (40) + 5 backup
        groups, backup, _ = assemble(players)
        assert len(groups) == 5
        assert len(backup) == 5
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    # --- exact multiples of 8: no backups left over ---

    def test_it_leaves_no_backup_for_a_roster_of_exactly_one_group(self):
        players = omni_roster(count=8, raid_leaders=1)
        groups, backup, _ = assemble(players)
        assert len(groups) == 1
        assert backup == []
        assert_valid_composition(groups[0])

    def test_it_leaves_no_backup_for_a_roster_of_exactly_three_groups(self):
        players = omni_roster(count=24, raid_leaders=4)
        groups, backup, _ = assemble(players)
        assert len(groups) == 3
        assert backup == []
        assert_no_player_used_twice(groups, backup, players)

    def test_it_leaves_no_backup_for_a_roster_of_exactly_five_groups(self):
        players = omni_roster(count=40, raid_leaders=6)
        groups, backup, _ = assemble(players)
        assert len(groups) == 5
        assert backup == []
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    # --- role scarcity as the limiting factor ---

    def test_tanks_limit_the_number_of_groups(self):
        # Only 4 tank-capable players in the whole roster (2 per group -> 2 groups).
        # Filler covers everything BUT tank, so tanks are genuinely the bottleneck.
        non_tank = tuple(r for r in ALL_ROLES if r != 'tank')
        tanks = [player(f'tank{i}', roles=('tank',)) for i in range(4)]
        filler = [player(f'o{i}', roles=non_tank, is_raid_leader=(i < 2)) for i in range(20)]
        players = tanks + filler
        groups, backup, _ = assemble(players)
        assert len(groups) == 2                      # 4 tank-capable // 2 per group
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    def test_a_single_healer_type_limits_the_number_of_groups(self):
        # Exactly 1 shield-capable player in the whole roster -> at most 1 group, even
        # though every other role is plentiful. Filler covers everything BUT shield.
        non_shield = tuple(r for r in ALL_ROLES if r != 'shield')
        shield = [player('theonlyshield', roles=('shield',))]
        filler = [player(f'o{i}', roles=non_shield, is_raid_leader=(i < 3)) for i in range(23)]
        players = shield + filler
        groups, backup, _ = assemble(players)
        assert len(groups) == 1                      # min(pure, shield) with shield == 1
        assert_valid_composition(groups[0])
        assert_no_player_used_twice(groups, backup, players)

    def test_two_scarce_roles_together_cap_the_group_count(self):
        # 6 tank-capable (-> up to 3 groups) but only 2 pure-capable (-> 2 groups): the
        # tighter bottleneck wins. Filler covers neither tank nor pure.
        neither = tuple(r for r in ALL_ROLES if r not in ('tank', 'pure'))
        tanks = [player(f'tank{i}', roles=('tank',)) for i in range(6)]
        pures = [player(f'pure{i}', roles=('pure',)) for i in range(2)]
        filler = [player(f'f{i}', roles=neither, is_raid_leader=(i < 2)) for i in range(20)]
        players = tanks + pures + filler
        groups, backup, _ = assemble(players)
        assert len(groups) == 2                      # min(6//2, pure=2) == 2
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    # --- raid leader abundance vs scarcity ---

    def test_every_group_has_a_raid_leader_when_leaders_are_abundant(self):
        players = omni_roster(count=40, raid_leaders=20)  # far more RLs than the 5 groups
        groups, backup, _ = assemble(players)
        assert len(groups) == 5
        for group in groups:
            assert group.has_raid_leader
            assert not group.needs_raid_leader

    def test_raid_leader_scarcity_caps_the_number_of_groups(self):
        # Enough players/roles for 4 groups, but only 2 raid leaders and no phantom allowed.
        players = omni_roster(count=32, raid_leaders=2)
        groups, backup, _ = assemble(players, phantom_rl=0)
        assert len(groups) == 2                      # capped by 2 raid leaders
        assert len(backup) == 32 - 16
        for group in groups:
            assert group.has_raid_leader

    def test_phantom_raid_leaders_extend_the_group_count_past_real_leaders(self):
        # 2 real leaders + allow 2 phantom -> 4 groups, last two leaderless.
        players = omni_roster(count=32, raid_leaders=2)
        groups, backup, _ = assemble(players, phantom_rl=2)
        assert len(groups) == 4
        real_led = [g for g in groups if not g.needs_raid_leader]
        phantom = [g for g in groups if g.needs_raid_leader]
        assert len(real_led) == 2
        assert len(phantom) == 2
        assert all(g.has_raid_leader for g in real_led)
        assert all(not g.has_raid_leader for g in phantom)

    def test_an_inflexible_raid_leader_is_seated_and_does_not_cost_a_group(self):
        # One caster-only RL among otherwise-omni RLs. It must still be seated (into a DPS
        # slot) rather than stranded, so all groups still form.
        omni_rls = [player(f'rl{i}', roles=ALL_ROLES, is_raid_leader=True) for i in range(2)]
        caster_only_rl = player('casteronly', roles=('caster',), is_raid_leader=True)
        filler = [player(f'f{i}', roles=ALL_ROLES) for i in range(21)]
        players = omni_rls + [caster_only_rl] + filler  # 24 total -> 3 groups
        groups, backup, _ = assemble(players)
        assert len(groups) == 3
        # The inflexible leader ended up in a group, not on the bench.
        assert all(p.username != 'casteronly' for p in backup)
        for group in groups:
            assert group.has_raid_leader
            assert_valid_composition(group)

    # --- DPS flavor coverage: standard vs relaxed (soft rule) ---

    def test_it_forms_standard_groups_when_all_dps_flavors_are_available(self):
        # Everyone can play every flavor, so each group covers all three -> standard.
        assembly = GroupAssembly(omni_roster(count=24, raid_leaders=3), seed=0)
        groups, _, _ = assembly.assemble_groups()
        assert len(groups) == 3
        assert all(g.is_standard() for g in groups)

    def test_it_relaxes_dps_flavor_when_a_flavor_is_unavailable(self):
        # A single group's worth of players where the 4 DPS slots can only be filled by
        # melee/caster -- no one can play ranged. The group must still form, but with a
        # non-standard (two-flavor) DPS composition.
        fixed = [
            player('tank1', roles=('tank',), is_raid_leader=True),
            player('tank2', roles=('tank',)),
            player('pure1', roles=('pure',)),
            player('shield1', roles=('shield',)),
        ]
        dps = [player(f'd{i}', roles=('melee', 'caster')) for i in range(4)]  # no ranged anywhere
        assembly = GroupAssembly(fixed + dps, seed=0)
        groups, backup, _ = assembly.assemble_groups()

        assert len(groups) == 1
        assert backup == []
        subject = groups[0]
        assert_valid_composition(subject)              # hard rule: still 2/1/1/4
        assert not subject.is_standard()               # soft rule relaxed: ranged missing
        assert subject.dps_flavors() == {'melee', 'caster'}

    # --- bench-first backups: backups only fill gaps regulars cannot cover ---

    def test_it_benches_backups_when_regulars_can_fill_every_slot(self):
        # 8 regulars can form the one group; 3 backups (also omni) must be benched.
        regulars = [player(f'r{i}', roles=ALL_ROLES, is_raid_leader=(i == 0)) for i in range(8)]
        backups = [player(f'b{i}', roles=ALL_ROLES, is_backup=True) for i in range(3)]
        groups, backup, _ = assemble(regulars + backups)
        assert len(groups) == 1
        # None of the grouped players is a backup; all backups sit on the bench.
        assert all(not p.is_backup for p in groups[0].members)
        assert {p.username for p in backup} == {'b0', 'b1', 'b2'}

    def test_it_uses_a_backup_only_to_fill_a_slot_no_regular_can_cover(self):
        # Regulars cover everything except shield; the sole shield player is a backup.
        # Bench-first must still pull that backup in, or the group can't form.
        non_shield = tuple(r for r in ALL_ROLES if r != 'shield')
        regulars = [player(f'r{i}', roles=non_shield, is_raid_leader=(i == 0)) for i in range(7)]
        shield_backup = player('shield_backup', roles=('shield',), is_backup=True)
        groups, backup, _ = assemble(regulars + [shield_backup])
        assert len(groups) == 1
        assert backup == []
        # The backup was used because no regular could shield.
        assert shield_backup in groups[0].members

    def test_it_prefers_a_non_backup_raid_leader_over_a_backup_one(self):
        # Two raid leaders available for one group: one regular, one backup. The regular
        # should be seated; the backup benched.
        regular_rl = player('regular_rl', roles=ALL_ROLES, is_raid_leader=True)
        backup_rl = player('backup_rl', roles=ALL_ROLES, is_raid_leader=True, is_backup=True)
        filler = [player(f'f{i}', roles=ALL_ROLES) for i in range(9)]
        groups, backup, _ = assemble([regular_rl, backup_rl] + filler)
        assert len(groups) == 1
        assert regular_rl in groups[0].members
        assert backup_rl in backup


class TestGroupAssemblyWithPairs:
    def _roster_with_pair(self):
        """16 omni players, two RLs, 'alice' and 'bob' are a pair."""
        return (
            [player('rl', is_raid_leader=True), player('rl2', is_raid_leader=True),
             player('alice'), player('bob')]
            + [player(f'f{i}') for i in range(12)]
        )

    def test_paired_players_end_up_in_the_same_group(self):
        players = self._roster_with_pair()
        pairs = {'Alice': 'Bob', 'Bob': 'Alice'}
        groups, _, _ = assemble(players, pairs=pairs)

        alice_group = next(i for i, g in enumerate(groups) if any(p.username == 'alice' for p in g.members))
        bob_group = next(i for i, g in enumerate(groups) if any(p.username == 'bob' for p in g.members))
        assert alice_group == bob_group

    def test_no_violated_pairs_when_pair_is_honoured(self):
        players = self._roster_with_pair()
        pairs = {'Alice': 'Bob', 'Bob': 'Alice'}
        _, _, violated = assemble(players, pairs=pairs)
        assert violated == []

    def test_violated_pair_is_recorded_when_partners_cannot_share_a_group(self):
        # alice is the sole shield; bob is DPS-only. With 8 players for 1 group they both
        # fit, but if the greedy fill separates them violated must record it.
        rl = make_player('rl', roles=ALL_ROLES, is_raid_leader=True)
        alice = make_player('alice', roles=('shield',))
        bob = make_player('bob', roles=('melee', 'ranged', 'caster'))
        tanks = [make_player(f'tank{i}', roles=('tank',)) for i in range(2)]
        pure = make_player('pure1', roles=('pure',))
        dps = [make_player(f'd{i}', roles=('melee', 'ranged', 'caster')) for i in range(3)]
        players = [rl, alice, bob, pure] + tanks + dps

        groups, _, violated = assemble(players, pairs={'Alice': 'Bob', 'Bob': 'Alice'})

        assert len(groups) == 1
        alice_in = any(p.username == 'alice' for p in groups[0].members)
        bob_in = any(p.username == 'bob' for p in groups[0].members)
        if not (alice_in and bob_in):
            assert ('Alice', 'Bob') in violated or ('Bob', 'Alice') in violated
        else:
            assert violated == []

    def test_violated_pair_when_one_member_ends_up_on_bench(self):
        rl = player('rl', is_raid_leader=True)
        alice = player('alice')
        bob = player('bob')
        fillers = [player(f'f{i}') for i in range(6)]
        extra = player('extra')  # 9th regular -> one goes to bench
        players = [rl, alice, bob] + fillers + [extra]

        groups, _, violated = assemble(players, pairs={'Alice': 'Bob', 'Bob': 'Alice'}, seed=0)

        assert len(groups) == 1
        alice_placed = any(p.username == 'alice' for p in groups[0].members)
        bob_placed = any(p.username == 'bob' for p in groups[0].members)
        if not (alice_placed and bob_placed):
            assert ('Alice', 'Bob') in violated or ('Bob', 'Alice') in violated

    def test_pair_violation_reported_only_once(self):
        rl = player('rl', is_raid_leader=True)
        fillers = [player(f'f{i}') for i in range(6)]
        extra = player('extra')
        players = [rl, player('alice'), player('bob')] + fillers + [extra]

        _, _, violated = assemble(players, pairs={'Alice': 'Bob', 'Bob': 'Alice'}, seed=0)

        canonical_count = sum(1 for p in violated if set(p) == {'Alice', 'Bob'})
        assert canonical_count <= 1

    def test_no_pairs_does_not_break_assembly(self):
        players = [player('rl', is_raid_leader=True)] + [player(f'p{i}') for i in range(7)]
        groups, backup, _ = assemble(players)
        assert len(groups) == 1
        assert backup == []

    def test_backup_pair_is_admitted_when_partner_is_already_in_group(self):
        # bob is a backup; alice is his partner and a regular. The bench-first rule is
        # relaxed when alice is already seated, so bob should join the group.
        rl = player('rl', is_raid_leader=True)
        alice = player('alice')
        bob = player('bob', is_backup=True)
        fillers = [player(f'f{i}') for i in range(6)]
        players = [rl, alice, bob] + fillers

        groups, _, violated = assemble(players, pairs={'Alice': 'Bob', 'Bob': 'Alice'}, seed=0)

        assert len(groups) == 1
        assert any(p.username == 'bob' for p in groups[0].members)
        assert violated == []

    def test_paired_first_ordering_prefers_player_whose_partner_is_already_seated(self):
        # One DPS slot left; two candidates of equal constraint: bob (partner alice already
        # in group) and unpaired. Bob must win.
        rl = make_player('rl', roles=ALL_ROLES, is_raid_leader=True)
        tank1 = make_player('tank1', roles=('tank',))
        tank2 = make_player('tank2', roles=('tank',))
        pure1 = make_player('pure1', roles=('pure',))
        shield1 = make_player('shield1', roles=('shield',))
        dps1 = make_player('dps1', roles=('melee',))
        dps2 = make_player('dps2', roles=('ranged',))
        dps3 = make_player('dps3', roles=('caster',))
        alice = make_player('alice', roles=('melee', 'ranged', 'caster'))
        bob = make_player('bob', roles=('melee', 'ranged', 'caster'))
        unpaired = make_player('unpaired', roles=('melee', 'ranged', 'caster'))

        players = [rl, tank1, tank2, pure1, shield1, dps1, dps2, dps3, alice, bob, unpaired]
        groups, _, _ = assemble(players, pairs={'Alice': 'Bob', 'Bob': 'Alice'}, seed=0)

        assert len(groups) == 1
        member_names = {p.username for p in groups[0].members}
        assert 'alice' in member_names
        assert 'bob' in member_names
        assert 'unpaired' not in member_names

    def test_assemble_groups_returns_violated_pairs_as_third_element(self):
        rl = player('rl', is_raid_leader=True)
        fillers = [player(f'f{i}') for i in range(6)]
        extra = player('extra')
        players = [rl, player('alice'), player('bob')] + fillers + [extra]

        _, _, violated = assemble(players, pairs={'Alice': 'Bob', 'Bob': 'Alice'}, seed=42)

        assert isinstance(violated, list)
        assert all(isinstance(v, tuple) and len(v) == 2 for v in violated)


class TestBalancerPairConstraint:
    def _two_group_setup(self, pairs):
        rl1 = player('rl1', is_raid_leader=True)
        rl2 = player('rl2', is_raid_leader=True)
        alice = player('alice')
        bob = player('bob')
        g1_fillers = [player(f'g1f{i}') for i in range(4)]
        g2_fillers = [player(f'g2f{i}') for i in range(6)]
        players = [rl1, rl2, alice, bob] + g1_fillers + g2_fillers
        groups, _, _ = assemble(players, pairs=pairs, seed=0)
        return groups

    def test_balancer_does_not_split_a_pair(self):
        pairs = {'Alice': 'Bob', 'Bob': 'Alice'}
        groups = self._two_group_setup(pairs)

        swap_members_for_balance(groups, pairs=pairs)

        alice_group = next(i for i, g in enumerate(groups) if any(p.username == 'alice' for p in g.members))
        bob_group = next(i for i, g in enumerate(groups) if any(p.username == 'bob' for p in g.members))
        assert alice_group == bob_group
