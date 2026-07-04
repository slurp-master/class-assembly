from lib.models import Player, Assignment


def make_player(username='alice', roles=('tank',)):
    return Player(
        username=username,
        global_name=username.title(),
        available_roles=frozenset(roles),
        is_backup=False,
    )


class TestAssignment:
    def test_it_exposes_its_players_experience(self):
        player = make_player(roles=('tank', 'pure', 'melee'))
        subject = Assignment(player=player, role='tank')
        assert subject.experience == 3

    def test_it_allows_a_swap_when_each_player_can_play_the_others_role(self):
        subject = Assignment(player=make_player(username='a', roles=('tank', 'melee')), role='tank')
        other = Assignment(player=make_player(username='b', roles=('tank', 'melee')), role='melee')
        assert subject.can_swap_with(other)

    def test_it_forbids_a_swap_when_this_player_cannot_play_the_others_role(self):
        subject = Assignment(player=make_player(username='a', roles=('tank',)), role='tank')
        other = Assignment(player=make_player(username='b', roles=('tank', 'melee')), role='melee')
        # subject's player cannot play 'melee', so the swap is invalid.
        assert not subject.can_swap_with(other)

    def test_it_forbids_a_swap_when_the_other_player_cannot_play_this_role(self):
        subject = Assignment(player=make_player(username='a', roles=('tank', 'melee')), role='tank')
        other = Assignment(player=make_player(username='b', roles=('melee',)), role='melee')
        # other's player cannot play 'tank', so the swap is invalid.
        assert not subject.can_swap_with(other)

    def test_it_allows_a_swap_between_players_sharing_the_same_role(self):
        subject = Assignment(player=make_player(username='a', roles=('tank',)), role='tank')
        other = Assignment(player=make_player(username='b', roles=('tank',)), role='tank')
        assert subject.can_swap_with(other)
