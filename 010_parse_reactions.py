import json
import pandas as pd
from pathlib import Path


def main():
    # Get all role files from omega directory
    omega_dir = Path('data/omega-2026-07-01')
    role_files = sorted(omega_dir.glob('*.json'))

    raid_leaders = [
        'Sand King',
        'Amberforge',
        'Irisviel',
        'Herm Frilaix',
        'Pufi',
        'Ebon',
        'Tytan',
        'wuCk',
        'Moldy',
        'Netherwind',
    ]

    # Extract role names (filename without extension, without number prefix)
    roles = [f.stem.split('-', 1)[1] for f in role_files]

    # Build role to user mapping and collect all unique users
    role_to_users = {}
    all_users_by_id = {}

    for role_file in role_files:
        role_name = role_file.stem.split('-', 1)[1]
        with open(role_file) as f:
            users_list = json.load(f)

        user_ids = set()
        for user in users_list:
            user_id = user['id']
            user_ids.add(user_id)
            # Store user data if not seen before
            if user_id not in all_users_by_id:
                all_users_by_id[user_id] = user

        role_to_users[role_name] = user_ids

    # Build data for dataframe
    data = []
    for user_id, user in all_users_by_id.items():
        row = {
            'username': user['username'],
            'global_name': user['global_name'],
        }
        for role in roles:
            row[role] = user_id in role_to_users.get(role, set())
        data.append(row)

    # Create dataframe and write to CSV
    df = pd.DataFrame(data)

    df['username'] = df['username'].replace({'': None})
    df['global_name'] = df['global_name'].fillna(df.username)

    # Raid leaders are provided out-of-band (not in the reaction JSON) by global_name.
    # Mark them as a boolean column so the grouper can enforce >=1 RL per group.
    df['raid_leader'] = df['global_name'].isin(raid_leaders)

    matched = set(df.loc[df['raid_leader'], 'global_name'])
    missing = [name for name in raid_leaders if name not in matched]
    if missing:
        print(f'WARNING: raid leaders not found among signups: {missing}')

    df.to_csv('./data/010_reactions/reactions.csv', index=False)
    print(f'Saved!')
    print(f'Total users: {len(df)}')
    print(f'Raid leaders matched: {len(matched)} of {len(raid_leaders)}')
    print(f'Columns: {list(df.columns)}')


if __name__ == '__main__':
    main()
