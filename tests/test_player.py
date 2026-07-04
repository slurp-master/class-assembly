from lib.models import Player


def make_player(username='alice', roles=('tank',), is_backup=False, is_raid_leader=False):
    return Player(
        username=username,
        global_name=username.title(),
        available_roles=frozenset(roles),
        is_backup=is_backup,
        is_raid_leader=is_raid_leader,
    )


class TestPlayer:
    def test_it_detects_what_roles_it_can_fill(self):
        subject = make_player(roles=('tank', 'melee'))
        assert subject.can('tank')
        assert subject.can('melee')
        assert not subject.can('pure')

    def test_it_reports_the_number_of_roles_it_can_fill(self):
        subject = make_player(roles=('tank', 'pure', 'melee'))
        assert subject.num_roles == 3

    def test_it_reports_zero_roles_when_it_can_fill_none(self):
        subject = make_player(roles=())
        assert subject.num_roles == 0

    def test_it_uses_role_count_as_the_experience_proxy(self):
        subject = make_player(roles=('tank', 'pure', 'shield', 'melee'))
        assert subject.experience == 4

    def test_it_orders_players_by_username(self):
        alice = make_player(username='alice')
        bob = make_player(username='bob')
        assert alice < bob
        assert sorted([bob, alice]) == [alice, bob]

    def test_it_defaults_to_not_being_a_raid_leader(self):
        subject = Player(username='u', global_name='U', available_roles=frozenset(), is_backup=False)
        assert not subject.is_raid_leader

    def test_it_remembers_when_it_is_a_raid_leader(self):
        subject = make_player(is_raid_leader=True)
        assert subject.is_raid_leader

    def test_it_is_hashable_so_it_can_live_in_sets(self):
        subject = make_player(username='alice')
        same = make_player(username='alice')
        assert {subject, same} == {subject}
