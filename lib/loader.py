import pandas as pd
from lib.models import Player

# The actual party roles. 'check' (attendance confirmation), 'backup', and 'raid_leader'
# are signup metadata, not roles, and must not end up in available_roles.
ROLE_COLUMNS = ['tank', 'pure', 'shield', 'caster', 'melee', 'ranged']


def load_players(csv_path: str) -> list[Player]:
    """Load players from reactions.csv"""
    df = pd.read_csv(csv_path)

    players = []

    for _, row in df.iterrows():
        available_roles = {role for role in ROLE_COLUMNS if pd.notna(row[role]) and row[role]}

        is_backup = pd.notna(row.get('backup')) and row['backup']
        is_raid_leader = pd.notna(row.get('raid_leader')) and row['raid_leader']

        player = Player(
            username=row['username'],
            global_name=row['global_name'],
            available_roles=frozenset(available_roles),
            is_backup=is_backup,
            is_raid_leader=is_raid_leader,
        )
        players.append(player)

    return players
