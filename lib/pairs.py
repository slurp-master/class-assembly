import csv
from lib.models import Player
from lib.logging_setup import setup_logging

PAIRS_CSV = 'data/000_pairs/pairs.csv'

logger = setup_logging(__name__)


def load_pairs(csv_path: str = PAIRS_CSV) -> list[tuple]:
    """Load raw pairs from CSV. Returns list of (name_1, name_2) tuples."""
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return [(row['name_1'].strip(), row['name_2'].strip()) for row in reader]
    except FileNotFoundError:
        raise FileNotFoundError(f'Pairs file not found: {csv_path}')


def build_pair_lookup(raw_pairs: list[tuple], players: list[Player]) -> dict[str, str]:
    """Build a bidirectional {global_name -> partner_global_name} lookup.

    Validation rules applied here:
    - Both members must be present among event signups to activate the pair. If
      only one signed up the pair is silently dropped (that player competes as
      unpaired). This is intentional: the pairs list is community-wide and grows
      independently of event signups.
    - Two raid leaders may not be paired (raises ValueError).
    """
    present = {p.global_name for p in players}
    rl_names = {p.global_name for p in players if p.is_raid_leader}

    lookup: dict[str, str] = {}

    for name_1, name_2 in raw_pairs:
        both_present = name_1 in present and name_2 in present
        one_present = name_1 in present or name_2 in present

        if not one_present:
            logger.debug(f'Pair ({name_1}, {name_2}): neither signed up, skipping')
            continue

        if not both_present:
            absent = name_2 if name_1 in present else name_1
            logger.warning(
                f'Pair ({name_1}, {name_2}): {absent!r} did not sign up — treating '
                f'the present member as unpaired'
            )
            continue

        if name_1 in rl_names and name_2 in rl_names:
            raise ValueError(
                f'Pair ({name_1}, {name_2}): pairing two raid leaders is not allowed'
            )

        lookup[name_1] = name_2
        lookup[name_2] = name_1
        logger.info(f'Pair activated: {name_1} <-> {name_2}')

    return lookup
