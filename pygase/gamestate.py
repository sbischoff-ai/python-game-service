# -*- coding: utf-8 -*-

import time

from pygase.utils import Sendable, NamedEnum, sqn

# unique 4-byte token to mark GameState entries for deletion
TO_DELETE = bytes.fromhex('d281e5ba')

class GameStateStore:

    _update_cache_size = 100

    def __init__(self):
        self._game_state = GameState()
        self._game_state_update_cache = [GameStateUpdate(0)]

    def get_update_cache(self):
        return self._game_state_update_cache.copy()

    def get_game_state(self):
        return self._game_state

    def push_update(self, update:GameStateUpdate):
        self._game_state_update_cache.append(update)
        if len(self._game_state_update_cache) > self._update_cache_size:
            del self._game_state_update_cache[0]
        if update > self._game_state:
            self._game_state += update

class GameStateMachine:
    '''
    This class is meant as a base class from which you inherit and implement the `update` method.
    '''
    def __init__(self):
        self.game_time = 0
        self._stop = True

    def run_game_loop(self, game_state_store, interval=0.02):
        if game_state_store.get_game_state().game_status == GameStatus.get('Paused'):
            game_state_store.push_update(
                GameStateUpdate(
                    game_state_store.get_game_state().time_order + 1,
                    game_status=GameStatus.get('Active')
                )
            )
        self._stop = False
        dt = interval
        while not self._stop:
            t0 = time.time()
            game_state_store.push_update(
                self.update(game_state_store.get_game_state(), dt)
            )
            dt = max(interval, time.time()-t0)
            if dt < interval:
                time.sleep(interval-dt)
                dt = interval
            self.game_time += dt
        if game_state_store.get_game_state().game_status == GameStatus.get('Active'):
            game_state_store.push_update(
                GameStateUpdate(
                    game_state_store.get_game_state().time_order + 1,
                    game_status=GameStatus.get('Paused')
                )
            )

    def stop(self):
        self._stop = True

    def update(self, game_state, dt):
        '''
        This method should be implemented to return a GameStateUpdate.
        '''
        raise NotImplementedError()

class GameStatus(NamedEnum): pass
GameStatus.register('Paused')
GameStatus.register('Active')

class GameState(Sendable):
    '''
    Contains game state information that is required to be known both by the server and the client.
    Since it is a *Sendable*, it can only contain attributes of type `str`, `bytes`, `sqn`, `int`, `float`,
    `bool` as well as `list`s or `tuple`s of such.

    *time_order* should be in alignment with the servers current update counter.
    '''

    def __init__(self, time_order=0, game_status=GameStatus.get('Paused'), **kwargs):
        self.__dict__ = kwargs
        self.game_status = game_status
        self.time_order = sqn(time_order)

    def is_paused(self):
        '''
        Returns *True* if game status is *Paused*.
        '''
        return self.game_status == GameStatus.get('Paused')

    '''
    Overrides of 'object' member functions
    '''
    # Check time ordering
    def __lt__(self, other):
        return self.time_order < other.time_order

    def __gt__(self, other):
        return self.time_order > other.time_order


class GameStateUpdate(Sendable):
    '''
    Represents a set of changes to carry out on a *GameState*.
    The server keeps a *time_order* counter and labels all updates in ascending order.

    Keywords are *GameState* attribute names. If you want to remove some key from the
    game state (*GameState* attributes themselves can also be deleted, which removes them from
    the object altogether), just assign *TO_DELETE* to it in the update.

    Use the *+* operator to add *GameStateUpdate*s together or to add them to a
    *GameState* (returning the updated update/state).

    Adding up available updates will always result in an equally or more current but
    also heavier update (meaning it will contain more data).
    '''

    def __init__(self, time_order:int, **kwargs):
        self.__dict__ = kwargs
        self.time_order = sqn(time_order)

    @classmethod
    def from_bytes(cls, bytepack:bytes):
        update = super().from_bytes(bytepack)
        update.time_order = sqn(update.time_order) # pylint: disable=no-member
        return update

    # Adding to another update should return an updated update
    def __add__(self, other):
        if other > self:
            _recursive_update(self.__dict__, other.__dict__)
            return self
        else:
            _recursive_update(other.__dict__, self.__dict__)
            return other

    # Adding to a GameState should update and return the state
    def __radd__(self, other):
        if type(other) is int:
            # This is so that sum() works on lists of updates, because
            # sum will always begin by adding the first element of the
            # list to 0.
            return self
        if self > other:
            _recursive_update(other.__dict__, self.__dict__, delete=True)
        return other

    # Check time ordering
    def __lt__(self, other):
        return self.time_order < other.time_order

    def __gt__(self, other):
        return self.time_order > other.time_order

# This is for GameStateUpdate objects, which should update nested
# dicts recursively so that no state data is unexpectedly deleted.
# Also, this functions manages deletion of state objects.
def _recursive_update(d: dict, u: dict, delete=False):
    for k, v in u.items():
        if v == TO_DELETE and delete and k in d.keys():
            del d[k]
        elif isinstance(v, dict) and k in d.keys() and isinstance(d[k], dict):
            _recursive_update(d[k], v, delete=delete)
        else:
            d[k] = v
