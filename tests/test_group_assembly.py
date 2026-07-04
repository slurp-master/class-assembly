from lib.models import Player, GROUP_SIZE, DPS_ROLES
from lib.grouper import GroupAssembly

ALL_ROLES = ('tank', 'pure', 'shield', 'melee', 'ranged', 'caster')


def player(username, roles=ALL_ROLES, is_raid_leader=False):
    return Player(
        username=username,
        global_name=username,
        available_roles=frozenset(roles),
        is_backup=False,
        is_raid_leader=is_raid_leader,
    )


def omni_roster(count, raid_leaders):
    """`count` players who can play every role; the first `raid_leaders` of them are RLs."""
    return [
        player(f'p{i}', roles=ALL_ROLES, is_raid_leader=(i < raid_leaders))
        for i in range(count)
    ]


def assemble(players, seed=0, phantom_rl=0):
    return GroupAssembly(players, seed=seed, phantom_rl=phantom_rl).assemble_groups()


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
        groups, backup = assemble(players)
        assert len(groups) == 1
        assert len(backup) == 3
        assert_valid_composition(groups[0])
        assert_no_player_used_twice(groups, backup, players)

    def test_it_forms_multiple_groups_from_a_generous_roster(self):
        players = omni_roster(count=27, raid_leaders=5)  # 3 full groups (24) + 3 backup
        groups, backup = assemble(players)
        assert len(groups) == 3
        assert len(backup) == 3
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    def test_it_forms_up_to_five_groups_when_the_roster_is_large(self):
        players = omni_roster(count=45, raid_leaders=8)  # 5 full groups (40) + 5 backup
        groups, backup = assemble(players)
        assert len(groups) == 5
        assert len(backup) == 5
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    # --- exact multiples of 8: no backups left over ---

    def test_it_leaves_no_backup_for_a_roster_of_exactly_one_group(self):
        players = omni_roster(count=8, raid_leaders=1)
        groups, backup = assemble(players)
        assert len(groups) == 1
        assert backup == []
        assert_valid_composition(groups[0])

    def test_it_leaves_no_backup_for_a_roster_of_exactly_three_groups(self):
        players = omni_roster(count=24, raid_leaders=4)
        groups, backup = assemble(players)
        assert len(groups) == 3
        assert backup == []
        assert_no_player_used_twice(groups, backup, players)

    def test_it_leaves_no_backup_for_a_roster_of_exactly_five_groups(self):
        players = omni_roster(count=40, raid_leaders=6)
        groups, backup = assemble(players)
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
        groups, backup = assemble(players)
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
        groups, backup = assemble(players)
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
        groups, backup = assemble(players)
        assert len(groups) == 2                      # min(6//2, pure=2) == 2
        for group in groups:
            assert_valid_composition(group)
        assert_no_player_used_twice(groups, backup, players)

    # --- raid leader abundance vs scarcity ---

    def test_every_group_has_a_raid_leader_when_leaders_are_abundant(self):
        players = omni_roster(count=40, raid_leaders=20)  # far more RLs than the 5 groups
        groups, backup = assemble(players)
        assert len(groups) == 5
        for group in groups:
            assert group.has_raid_leader
            assert not group.needs_raid_leader

    def test_raid_leader_scarcity_caps_the_number_of_groups(self):
        # Enough players/roles for 4 groups, but only 2 raid leaders and no phantom allowed.
        players = omni_roster(count=32, raid_leaders=2)
        groups, backup = assemble(players, phantom_rl=0)
        assert len(groups) == 2                      # capped by 2 raid leaders
        assert len(backup) == 32 - 16
        for group in groups:
            assert group.has_raid_leader

    def test_phantom_raid_leaders_extend_the_group_count_past_real_leaders(self):
        # 2 real leaders + allow 2 phantom -> 4 groups, last two leaderless.
        players = omni_roster(count=32, raid_leaders=2)
        groups, backup = assemble(players, phantom_rl=2)
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
        groups, backup = assemble(players)
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
        groups, _ = assembly.assemble_groups()
        assert len(groups) == 3
        assert all(g.is_standard() for g in groups)
        assert assembly.non_standard_groups == 0

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
        groups, backup = assembly.assemble_groups()

        assert len(groups) == 1
        assert backup == []
        subject = groups[0]
        assert_valid_composition(subject)              # hard rule: still 2/1/1/4
        assert not subject.is_standard()               # soft rule relaxed: ranged missing
        assert subject.dps_flavors() == {'melee', 'caster'}
        assert assembly.non_standard_groups == 1
