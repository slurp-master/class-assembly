import pytest
from lib.pairs import build_pair_lookup
from tests.factories import make_player

ALL_ROLES = ('tank', 'pure', 'shield', 'melee', 'ranged', 'caster')


def omni(username, is_raid_leader=False):
    return make_player(username, roles=ALL_ROLES, is_raid_leader=is_raid_leader)


class TestBuildPairLookup:
    def test_it_activates_a_pair_when_both_players_signed_up(self):
        players = [omni('alice'), omni('bob')]
        lookup = build_pair_lookup([('Alice', 'Bob')], players)
        assert lookup == {'Alice': 'Bob', 'Bob': 'Alice'}

    def test_it_is_bidirectional(self):
        players = [omni('alice'), omni('bob')]
        lookup = build_pair_lookup([('Alice', 'Bob')], players)
        assert lookup['Alice'] == 'Bob'
        assert lookup['Bob'] == 'Alice'

    def test_it_drops_pair_when_only_one_member_signed_up(self):
        players = [omni('alice')]
        lookup = build_pair_lookup([('Alice', 'Ghost')], players)
        assert lookup == {}

    def test_it_drops_pair_when_neither_member_signed_up(self):
        players = [omni('carol')]
        lookup = build_pair_lookup([('Alice', 'Bob')], players)
        assert lookup == {}

    def test_it_raises_for_rl_x_rl_pair(self):
        players = [omni('rl1', is_raid_leader=True), omni('rl2', is_raid_leader=True)]
        with pytest.raises(ValueError, match='raid leader'):
            build_pair_lookup([('Rl1', 'Rl2')], players)

    def test_it_allows_rl_paired_with_non_rl(self):
        players = [omni('rl1', is_raid_leader=True), omni('bob')]
        lookup = build_pair_lookup([('Rl1', 'Bob')], players)
        assert 'Rl1' in lookup

    def test_it_handles_multiple_pairs(self):
        players = [omni('alice'), omni('bob'), omni('carol'), omni('dave')]
        raw = [('Alice', 'Bob'), ('Carol', 'Dave')]
        lookup = build_pair_lookup(raw, players)
        assert lookup['Alice'] == 'Bob'
        assert lookup['Carol'] == 'Dave'
        assert len(lookup) == 4
