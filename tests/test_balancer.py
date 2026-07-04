from collections import Counter

from lib.models import Group
from lib.balancer import calculate_group_imbalance, swap_members_for_balance
from tests.factories import make_player as player


def group(assignments, needs_raid_leader=False):
    """Build a group directly from (player, role) pairs."""
    g = Group(needs_raid_leader=needs_raid_leader)
    for p, role in assignments:
        g.add(p, role)
    return g


def role_counts(g):
    return Counter(a.role for a in g.assignments)


class TestCalculateGroupImbalance:
    def test_it_is_zero_for_no_groups(self):
        assert calculate_group_imbalance([]) == 0.0

    def test_it_is_zero_for_a_single_group(self):
        subject = group([(player('a', ('tank', 'melee')), 'tank')])
        assert calculate_group_imbalance([subject]) == 0.0

    def test_it_is_zero_when_all_groups_share_the_same_experience(self):
        # Each group has one member with two roles -> experience 2 each.
        g1 = group([(player('a', ('tank', 'melee')), 'tank')])
        g2 = group([(player('b', ('pure', 'ranged')), 'pure')])
        assert calculate_group_imbalance([g1, g2]) == 0.0

    def test_it_reports_the_standard_deviation_of_group_experiences(self):
        # Experiences 1 and 3 -> mean 2, variance ((1)^2 + (1)^2)/2 = 1 -> std dev 1.0.
        g1 = group([(player('a', ('tank',)), 'tank')])                       # experience 1
        g2 = group([(player('b', ('tank', 'melee', 'ranged')), 'tank')])     # experience 3
        assert calculate_group_imbalance([g1, g2]) == 1.0


def phantom_group(assignments):
    """A group with no raid-leader requirement, so the RL guard never blocks swaps --
    lets the balance tests isolate the experience-balancing behavior."""
    return group(assignments, needs_raid_leader=True)


class TestSwapMembersForBalance:
    def test_it_makes_no_swaps_when_groups_are_already_balanced(self):
        g1 = phantom_group([(player('a', ('tank', 'melee')), 'tank'),
                            (player('b', ('tank', 'melee')), 'melee')])
        g2 = phantom_group([(player('c', ('tank', 'melee')), 'tank'),
                            (player('d', ('tank', 'melee')), 'melee')])
        swaps = swap_members_for_balance([g1, g2])
        assert swaps == 0

    def test_it_swaps_to_reduce_imbalance(self):
        # g1 holds the two low-experience players, g2 the two high-experience ones.
        # A tank<->tank swap between a low and a high player evens the groups out.
        low_tank = player('low_tank', ('tank',))                        # exp 1
        low_melee = player('low_melee', ('melee',))                     # exp 1
        high_tank = player('high_tank', ('tank', 'pure', 'shield'))     # exp 3
        high_melee = player('high_melee', ('melee', 'pure', 'shield'))  # exp 3
        g1 = phantom_group([(low_tank, 'tank'), (low_melee, 'melee')])    # experience 2
        g2 = phantom_group([(high_tank, 'tank'), (high_melee, 'melee')])  # experience 6

        before = calculate_group_imbalance([g1, g2])
        swaps = swap_members_for_balance([g1, g2])
        after = calculate_group_imbalance([g1, g2])

        assert swaps > 0
        assert after < before

    def test_it_preserves_each_groups_role_composition(self):
        g1 = phantom_group([(player('a', ('tank', 'melee')), 'tank'),
                            (player('b', ('melee', 'ranged')), 'melee')])
        g2 = phantom_group([(player('c', ('tank', 'melee', 'ranged')), 'tank'),
                            (player('d', ('melee', 'ranged', 'caster')), 'melee')])
        before1, before2 = role_counts(g1), role_counts(g2)

        swap_members_for_balance([g1, g2])

        assert role_counts(g1) == before1
        assert role_counts(g2) == before2

    def test_it_never_swaps_players_who_cannot_play_each_others_role(self):
        # The heavy and light groups are badly imbalanced, so a swap would help -- but
        # every cross-group pair is role-incompatible (all specialists, no shared roles),
        # so no legal swap exists and the groups are left untouched.
        tank_only = player('tank_only', ('tank',))          # exp 1
        ranged_only = player('ranged_only', ('ranged',))    # exp 1
        rich_melee = player('rich_melee', ('melee', 'pure', 'shield'))    # exp 3
        rich_caster = player('rich_caster', ('caster', 'pure', 'shield'))  # exp 3
        g1 = phantom_group([(tank_only, 'tank'), (ranged_only, 'ranged')])  # experience 2
        g2 = phantom_group([(rich_melee, 'melee'), (rich_caster, 'caster')])  # experience 6

        swaps = swap_members_for_balance([g1, g2])

        assert swaps == 0
        assert set(g1.members) == {tank_only, ranged_only}
        assert set(g2.members) == {rich_melee, rich_caster}

    def test_it_never_strips_a_group_of_its_only_raid_leader(self):
        # g1 is the heavy group; both a tank<->tank swap (which moves its sole raid leader
        # out) and a melee<->melee swap would improve balance. The guard must forbid the
        # raid-leader move, so balancing happens via the melee swap and g1 keeps its RL.
        leader = player('leader', ('tank', 'pure', 'shield'), is_raid_leader=True)  # exp 3
        high_melee = player('high_melee', ('melee', 'pure', 'shield'))             # exp 3
        low_tank = player('low_tank', ('tank',))                                   # exp 1
        low_melee = player('low_melee', ('melee',))                                # exp 1
        g1 = group([(leader, 'tank'), (high_melee, 'melee')])   # experience 6, sole RL
        g2 = group([(low_tank, 'tank'), (low_melee, 'melee')],
                   needs_raid_leader=True)                      # experience 2, phantom

        swaps = swap_members_for_balance([g1, g2])

        assert swaps > 0                       # balance still improved (via the melee swap)
        assert g1.has_raid_leader              # ...but the raid leader was never moved out
        assert leader in g1.members

    def test_it_allows_swapping_a_raid_leader_out_of_a_phantom_group(self):
        # Both groups are phantom (no RL requirement), so a balance-improving swap that
        # moves the raid leader is allowed.
        leader = player('leader', ('tank', 'pure', 'shield'), is_raid_leader=True)  # exp 3
        high_melee = player('high_melee', ('melee', 'pure', 'shield'))             # exp 3
        low_tank = player('low_tank', ('tank',))                                   # exp 1
        low_melee = player('low_melee', ('melee',))                                # exp 1
        g1 = phantom_group([(leader, 'tank'), (high_melee, 'melee')])   # experience 6
        g2 = phantom_group([(low_tank, 'tank'), (low_melee, 'melee')])  # experience 2

        before = calculate_group_imbalance([g1, g2])
        swaps = swap_members_for_balance([g1, g2])
        after = calculate_group_imbalance([g1, g2])

        assert swaps > 0
        assert after < before
        # The raid leader was free to move out of its phantom group.
        assert not g1.has_raid_leader
