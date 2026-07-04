from lib.models import Player


def make_player(username='alice', roles=('tank',), is_backup=False, is_raid_leader=False):
    """Build a Player for tests. All fields default so a call can be as terse or as
    specific as a test needs (``make_player()`` for a throwaway, ``make_player('rl',
    is_raid_leader=True)`` for a specific one)."""
    return Player(
        username=username,
        global_name=username.title(),
        available_roles=frozenset(roles),
        is_backup=is_backup,
        is_raid_leader=is_raid_leader,
    )
