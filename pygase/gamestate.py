# -*- coding: utf-8 -*-
"""Customize a game state model and apply state updates.
"""

from pygase.utils import Sendable, NamedEnum, Sqn

# unique 4-byte token to mark GameState entries for deletion
TO_DELETE: bytes = bytes.fromhex("d281e5ba")


class GameStatus(NamedEnum):

    """Enum for the game simulation status:
     - `'Paused'`
     - `'Active'`

    """


GameStatus.register("Paused")
GameStatus.register("Active")


class GameState(Sendable):

    """Customize a serializable game state model.

    Contains game state information that will be synchronized between the server and the clients.
    Via `pygase.utils.Sendable` its instances will be serialized using the msgpack protocol
    and must only contain attributes of type `str`, `bytes`, `Sqn`, `int`, `float`, `bool`
    as well as `list`s or `tuple`s of such.

    #### Optional Arguments
     - `time_order`: current time order number of the game state, higher means more recent
     - `game_status`: `GameStatus` enum value that describes whether or not the game loop is running

    #### Keyword Arguments
    Provide custom game state attributes via keyword arguments or assign them later.

    #### Attributes
      - `game_status`
      - `time_order`
    `GameState` instances mainly consist of custom attributes that make up the game state.

    """

    def __init__(self, time_order: int = 0, game_status: int = GameStatus.get("Paused"), **kwargs):
        self.__dict__ = kwargs
        self.game_status = game_status
        self.time_order = Sqn(time_order)

    def is_paused(self) -> bool:
        """Return `True` if game is paused."""
        return self.game_status == GameStatus.get("Paused")

    # Check time ordering
    def __lt__(self, other) -> bool:
        return self.time_order < other.time_order

    def __gt__(self, other) -> bool:
        return self.time_order > other.time_order


class GameStateUpdate(Sendable):

    """Update a `GameState` object.

    Contains a set of changes to carry out on a `GameState`.
    The server keeps a `time_order` counter and labels all updates in ascending order.

    Attributes of a `GameStateUpdate` object represent new values of `GameState` attributes.
    To remove game state attributes just assign `TO_DELETE` to it in the update.

    Use the `+` operator to add updates to one another and combine them or to add them to a
    game state in order to update it.

    #### Arguments
     - `time_order`: the time order up to which the update reaches

    #### Keyword Arguments
    game state attributes to be updated

    #### Attributes
     - `time_order`
    `GameStateUpdate` instances mainly consist of custom game state attributes to update.

    """

    def __init__(self, time_order: int, **kwargs):
        self.__dict__ = kwargs
        self.time_order = Sqn(time_order)

    @classmethod
    def from_bytes(cls, bytepack: bytes) -> "GameStateUpdate":
        """Extend `Sendable.from_bytes` to make sure time_order is of type `Sqn`."""
        update = super().from_bytes(bytepack)
        update.time_order = Sqn(update.time_order)  # pylint: disable=no-member
        return update

    def __add__(self, other: "GameStateUpdate") -> "GameStateUpdate":
        """Combine two updates."""
        if other > self:
            _recursive_update(self.__dict__, other.__dict__)
            return self
        _recursive_update(other.__dict__, self.__dict__)
        return other

    def __radd__(self, other):
        """Update a `GameState`."""
        if isinstance(other, int):
            # This is so that sum() works on lists of updates, because
            # sum will always begin by adding the first element of the
            # list to 0.
            return self
        if self > other:
            _recursive_update(other.__dict__, self.__dict__, delete=True)
        return other

    # Check time ordering
    def __lt__(self, other) -> bool:
        return self.time_order < other.time_order

    def __gt__(self, other) -> bool:
        return self.time_order > other.time_order


def _recursive_update(my_dict: dict, update_dict: dict, delete: bool = False) -> None:
    """Update nested dicts deeply via recursion."""
    for key, value in update_dict.items():
        if value == TO_DELETE and delete and key in my_dict.keys():
            del my_dict[key]
        elif isinstance(value, dict) and key in my_dict.keys() and isinstance(my_dict[key], dict):
            _recursive_update(my_dict[key], value, delete=delete)
        else:
            my_dict[key] = value
