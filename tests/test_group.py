from lib.models import Player, Group, GROUP_SIZE


def make_player(username='alice', roles=('tank',), is_raid_leader=False):
    return Player(
        username=username,
        global_name=username.title(),
        available_roles=frozenset(roles),
        is_backup=False,
        is_raid_leader=is_raid_leader,
    )


def fill_group(group, roles):
    """Add one distinct player per role, each able to play only that role."""
    for i, role in enumerate(roles):
        group.add(make_player(username=f'p{i}', roles=(role,)), role)


# A valid, standard 8-person composition: 2 tank, 1 pure, 1 shield, all three DPS flavors.
STANDARD_ROLES = ['tank', 'tank', 'pure', 'shield', 'melee', 'ranged', 'caster', 'melee']


class TestGroup:
    def test_it_correctly_adds_a_player(self):
        subject = Group()
        player = make_player(username='alice', roles=('tank',))
        subject.add(player, 'tank')
        assert subject.members == [player]

    def test_it_is_not_full_before_reaching_group_size(self):
        subject = Group()
        fill_group(subject, STANDARD_ROLES[:GROUP_SIZE - 1])
        assert not subject.is_full()

    def test_it_is_full_once_it_has_group_size_members(self):
        subject = Group()
        fill_group(subject, STANDARD_ROLES)
        assert subject.is_full()

    def test_it_sums_member_experience(self):
        subject = Group()
        subject.add(make_player(username='a', roles=('tank', 'melee')), 'tank')       # experience 2
        subject.add(make_player(username='b', roles=('pure', 'shield', 'melee')), 'pure')  # experience 3
        assert subject.experience == 5

    def test_it_reports_the_dps_flavors_it_contains(self):
        subject = Group()
        subject.add(make_player(username='a', roles=('melee',)), 'melee')
        subject.add(make_player(username='b', roles=('caster',)), 'caster')
        subject.add(make_player(username='t', roles=('tank',)), 'tank')
        assert subject.dps_flavors() == {'melee', 'caster'}

    def test_it_is_standard_when_all_three_dps_flavors_are_present(self):
        subject = Group()
        fill_group(subject, STANDARD_ROLES)
        assert subject.is_standard()

    def test_it_is_not_standard_when_a_dps_flavor_is_missing(self):
        subject = Group()
        # 4 DPS but only two flavors (melee, caster) -- ranged missing.
        fill_group(subject, ['tank', 'tank', 'pure', 'shield', 'melee', 'melee', 'caster', 'caster'])
        assert not subject.is_standard()

    def test_it_counts_its_raid_leaders(self):
        subject = Group()
        subject.add(make_player(username='a', is_raid_leader=True), 'tank')
        subject.add(make_player(username='b', is_raid_leader=True), 'tank')
        subject.add(make_player(username='c'), 'pure')
        assert subject.raid_leader_count == 2

    def test_it_detects_when_it_has_a_raid_leader(self):
        subject = Group()
        subject.add(make_player(username='a', is_raid_leader=True), 'tank')
        assert subject.has_raid_leader

    def test_it_detects_when_it_has_no_raid_leader(self):
        subject = Group()
        subject.add(make_player(username='a'), 'tank')
        assert not subject.has_raid_leader

    def test_it_requires_one_raid_leader_by_default(self):
        subject = Group()
        assert subject.required_raid_leaders == 1

    def test_it_requires_no_raid_leader_when_it_is_phantom(self):
        subject = Group(needs_raid_leader=True)
        assert subject.required_raid_leaders == 0

    def test_it_allows_a_swap_that_keeps_its_only_raid_leader(self):
        subject = Group()
        leader = make_player(username='rl', is_raid_leader=True)
        subject.add(leader, 'tank')
        mine = subject.assignments[0]
        incoming = make_player(username='incoming', is_raid_leader=True)
        assert subject.swap_keeps_raid_leader(mine, incoming)

    def test_it_rejects_a_swap_that_removes_its_only_raid_leader(self):
        subject = Group()
        leader = make_player(username='rl', is_raid_leader=True)
        subject.add(leader, 'tank')
        mine = subject.assignments[0]
        incoming = make_player(username='ordinary', is_raid_leader=False)
        assert not subject.swap_keeps_raid_leader(mine, incoming)

    def test_it_allows_dropping_a_raid_leader_when_a_phantom_group_needs_none(self):
        subject = Group(needs_raid_leader=True)
        leader = make_player(username='rl', is_raid_leader=True)
        subject.add(leader, 'tank')
        mine = subject.assignments[0]
        incoming = make_player(username='ordinary', is_raid_leader=False)
        assert subject.swap_keeps_raid_leader(mine, incoming)

    def test_it_swaps_two_players_between_groups_preserving_roles(self):
        subject = Group()
        other = Group()
        mine_player = make_player(username='mine', roles=('tank', 'melee'))
        their_player = make_player(username='theirs', roles=('tank', 'melee'))
        subject.add(mine_player, 'tank')
        other.add(their_player, 'melee')
        mine = subject.assignments[0]
        theirs = other.assignments[0]

        subject.swap(mine, other, theirs)

        assert subject.members == [their_player]
        assert other.members == [mine_player]
        # Each took over the other's role slot.
        assert subject.assignments[0].role == 'tank'
        assert other.assignments[0].role == 'melee'

    def test_it_orders_members_by_role_availability_then_name(self):
        subject = Group()
        # An omni-role player should sort ahead of a caster-only one regardless of name.
        omni = make_player(username='zzz', roles=('tank', 'pure', 'shield', 'melee', 'ranged', 'caster'))
        caster_only = make_player(username='aaa', roles=('caster',))
        subject.add(caster_only, 'caster')
        subject.add(omni, 'tank')
        ordered = [a.player for a in subject.ordered_members()]
        assert ordered == [omni, caster_only]
