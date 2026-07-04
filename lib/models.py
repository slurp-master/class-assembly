from dataclasses import dataclass


@dataclass(frozen=True)
class Player:
    username: str
    global_name: str
    available_roles: frozenset
    is_backup: bool

    @property
    def num_roles(self) -> int:
        """Number of roles this player can fill (used for constrainedness)"""
        return len(self.available_roles)

    @property
    def experience(self) -> int:
        """Numeric experience for this player.

        Real experience indicators are not wired up yet; for now we use the number of
        roles a player signed up for as a proxy (more flexible players tend to be more
        experienced). This property is the single place experience is produced -- swapping
        in a real source later only touches here. Nothing else should read ``num_roles``
        for balancing purposes.
        """
        return self.num_roles

    def can(self, role: str) -> bool:
        return role in self.available_roles

    def __lt__(self, other):
        """Define ordering for deterministic sorting"""
        return self.username < other.username


@dataclass(frozen=True)
class Assignment:
    """A player placed into a group for a specific role."""
    player: Player
    role: str

    @property
    def experience(self) -> int:
        return self.player.experience

    def can_swap_with(self, other: 'Assignment') -> bool:
        """A swap keeps both groups' compositions valid iff each player can play the
        other's assigned role -- this assignment takes ``other``'s role slot and vice
        versa."""
        return self.player.can(other.role) and other.player.can(self.role)
