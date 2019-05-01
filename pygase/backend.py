# -*- coding: utf-8 -*-
"""Serve PyGaSe clients.

Provides the `Server` class and all PyGaSe components that deal with progression and syncing of game states.

# Contents
- #GameStateStore: main API class for game state repositories
- #Server: main API class for PyGaSe servers
- #GameStateMachine: main API class for game logic components

"""

import time
import threading

import curio
from curio import socket
from curio.meta import awaitable

from pygase.connection import ServerConnection
from pygase.gamestate import GameState, GameStateUpdate, GameStatus
from pygase.event import UniversalEventHandler, Event


class GameStateStore:

    """Provide access to a game state and manage state updates.

    # Arguments
    inital_game_state (GameState): state of the game before the simulation begins

    """

    _update_cache_size: int = 100

    def __init__(self, initial_game_state: GameState = None):
        self._game_state = initial_game_state if initial_game_state is not None else GameState()
        self._game_state_update_cache = [GameStateUpdate(0)]

    def get_update_cache(self) -> list:
        """Return the latest state updates."""
        return self._game_state_update_cache.copy()

    def get_game_state(self) -> GameState:
        """Return the current game state."""
        return self._game_state

    def push_update(self, update: GameStateUpdate) -> None:
        """Push a new state update to the update cache.

        This method will usually be called by whatever is progressing the game state,
        usually a #GameStateMachine.

        """
        self._game_state_update_cache.append(update)
        if len(self._game_state_update_cache) > self._update_cache_size:
            del self._game_state_update_cache[0]
        if update > self._game_state:
            self._game_state += update


class Server:

    """Listen to clients and orchestrate the flow of events and state updates.

    The #Server instance does not contain game logic or state, it is only responsible for connections
    to clients. The state is provided by a #GameStateStore and game logic by a #GameStateMachine.

    # Arguments
    game_state_store (GameStateStore): part of the backend that provides an interface to the #pygase.GameState

    # Attributes
    connections (list): contains each clients address as a key leading to the
        corresponding #pygase.connection.ServerConnection instance
    host_client (tuple): address of the host client (who has permission to shutdown the server), if there is any
    game_state_store (GameStateStore): game state repository

    # Members
    hostname (str): read-only access to the servers hostname
    port (int): read-only access to the servers port number

    """

    def __init__(self, game_state_store: GameStateStore):
        self.connections: dict = {}
        self.host_client: tuple = None
        self.game_state_store = game_state_store
        self._universal_event_handler = UniversalEventHandler()
        self._hostname: str = None
        self._port: int = None

    def run(self, port: int = 0, hostname: str = "localhost", event_wire=None) -> None:
        """Start the server under a specified address.

        This is a blocking function but can also be spawned as a coroutine or in a thread
        via #Server.run_in_thread().

        # Arguments
        port (int): port number the server will be bound to, default will be an available
           port chosen by the computers network controller
        hostname (str): hostname or IP address the server will be bound to.
           Defaults to `'localhost'`.
        event_wire (GameStateMachine): object to which events are to be repeated
           (has to implement a `_push_event(event)` method and is typically a #GameStateMachine)

        """
        curio.run(self.run, port, hostname, event_wire)

    @awaitable(run)
    async def run(  # pylint: disable=function-redefined
        self, port: int = 0, hostname: str = "localhost", event_wire=None
    ) -> None:
        # pylint: disable=missing-docstring
        await ServerConnection.loop(hostname, port, self, event_wire)

    def run_in_thread(
        self, port: int = 0, hostname: str = "localhost", event_wire=None, daemon=True
    ) -> threading.Thread:
        """Start the server in a seperate thread.

        See #Server.run().

        # Returns
        threading.Thread: the thread the server loop runs in

        """
        thread = threading.Thread(target=self.run, args=(port, hostname, event_wire), daemon=daemon)
        thread.start()
        return thread

    @property
    def hostname(self) -> str:
        """Get the hostname or IP address on which the server listens.

        Returns `None` when the server is not running.

        """
        return "localhost" if self._hostname == "127.0.0.1" else self._hostname

    @property
    def port(self) -> int:
        """Get the port number on which the server listens.

        Returns `None` when the server is not running.

        """
        return self._port

    def shutdown(self) -> None:
        """Shut down the server.

        The server can be restarted via #Server.run() in which case it will remember previous connections.
        This method can also be spawned as a coroutine.

        """
        curio.run(self.shutdown)

    @awaitable(shutdown)
    async def shutdown(self) -> None:  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        async with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            await sock.sendto("shut_me_down".encode("utf-8"), (self._hostname, self._port))

    # advanced type checking for target client and callback would be helpful
    def dispatch_event(
        self, event_type: str, *args, target_client="all", retries: int = 0, ack_callback=None, **kwargs
    ) -> None:
        """Send an event to one or all clients.

        # Arguments
        event_type (str): identifies the event and links it to a handler
        target_client (tuple, str): either `'all'` for an event broadcast, or a clients address as a tuple
        retries (int): number of times the event is to be resent in case it times out
        ack_callback (callable, coroutine): will be executed after the event was received
            and be passed a reference to the corresponding #pygase.connection.ServerConnection instance
        Additional positional and keyword arguments will be sent as event data and passed to the clients
        handler function.

        """
        event = Event(event_type, *args, **kwargs)

        def get_ack_callback(connection):
            return lambda: ack_callback(connection)

        if retries > 0:

            def get_timeout_callback(connection):
                return lambda: self.dispatch_event(
                    event_type, *args, connection=connection, retries=retries - 1, ack_callback=ack_callback, **kwargs
                )

        else:

            def get_timeout_callback(connection):  # pylint: disable=unused-argument
                return None

        if target_client == "all":
            for connection in self.connections.values():
                connection.dispatch_event(
                    event, get_ack_callback(connection), get_timeout_callback(connection), **kwargs
                )
        else:
            self.connections[target_client].dispatch_event(
                event,
                get_ack_callback(self.connections[target_client]),
                get_timeout_callback(self.connections[target_client]),
                **kwargs,
            )

    # add advanced type checking for handler functions
    def register_event_handler(self, event_type: str, event_handler_function) -> None:
        """Register an event handler for a specific event type.

        # Arguments
        event_type (str): event type to link the handler function to
        handler_func (callable, coroutine): will be called for received events of the given type

        """
        self._universal_event_handler.register_event_handler(event_type, event_handler_function)


class GameStateMachine:

    """Run a simulation that propagates the game state.

    A #GameStateMachine progresses a game state through time, applying all game simulation logic.
    This class is meant either as a base class from which you inherit and implement the #GameStateMachine.time_step()
    method, or you assign an implementation after instantiation.

    # Arguments
    game_state_store (GameStateStore): part of the PyGaSe backend that provides the state

    # Attributes
    game_time (float): duration the game has been running in seconds

    """

    def __init__(self, game_state_store: GameStateStore):
        self.game_time: float = 0.0
        self._event_queue = curio.UniversalQueue()
        self._universal_event_handler = UniversalEventHandler()
        self._game_state_store = game_state_store
        self._game_loop_is_running = False

    def _push_event(self, event: Event) -> None:
        """Push an event into the state machines event queue.

        This method can be spawned as a coroutine.

        """
        self._event_queue.put(event)

    @awaitable(_push_event)
    async def _push_event(self, event: Event) -> None:  # pylint: disable=function-redefined
        await self._event_queue.put(event)

    # advanced type checking for the handler function would be helpful
    def register_event_handler(self, event_type: str, event_handler_function) -> None:
        """Register an event handler for a specific event type.

        For event handlers to have any effect, the events have to be wired from a #Server to
        the #GameStateMachine via the `event_wire` argument of the #Server.run() method.

        # Arguments
        event_type (str): which type of event to link the handler function to
        handler_func (callable, coroutine): function or coroutine to be invoked for events of the given type,
            gets passed the keyword argument `game_state` (along with those attached to the event)
            and is expected to return an update dict

        """
        self._universal_event_handler.register_event_handler(event_type, event_handler_function)

    def run_game_loop(self, interval: float = 0.02) -> None:
        """Simulate the game world.

        This function blocks as it continously progresses the game state through time
        but it can also be spawned as a coroutine or in a thread via #Server.run_game_loop_in_thread().
        As long as the simulation is running, the `game_state.status` will be `GameStatus.get('Active')`.

        # Arguments
        interval (float): (minimum) duration in seconds between consecutive time steps

        """
        curio.run(self.run_game_loop, interval)

    @awaitable(run_game_loop)
    async def run_game_loop(self, interval: float = 0.02) -> None:  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        if self._game_state_store.get_game_state().game_status == GameStatus.get("Paused"):
            self._game_state_store.push_update(
                GameStateUpdate(
                    self._game_state_store.get_game_state().time_order + 1, game_status=GameStatus.get("Active")
                )
            )
        game_state = self._game_state_store.get_game_state()
        dt = interval
        self._game_loop_is_running = True
        while game_state.game_status == GameStatus.get("Active"):
            t0 = time.time()
            update_dict = self.time_step(game_state, dt)
            while not self._event_queue.empty():
                event = await self._event_queue.get()
                event_update = await self._universal_event_handler.handle(event, game_state=game_state, dt=dt)
                update_dict.update(event_update)
                if time.time() - t0 > 0.95 * interval:
                    break
            self._game_state_store.push_update(GameStateUpdate(game_state.time_order + 1, **update_dict))
            game_state = self._game_state_store.get_game_state()
            dt = max(interval, time.time() - t0)
            await curio.sleep(max(0, interval - dt))
            self.game_time += dt
        self._game_loop_is_running = False

    def run_game_loop_in_thread(self, interval: float = 0.02) -> threading.Thread:
        """Simulate the game in a seperate thread.

        See #GameStateMachine.run_game_loop().

        # Returns
        threading.Thread: the thread the game loop runs in

        """
        thread = threading.Thread(target=self.run_game_loop, args=(interval,))
        thread.start()
        return thread

    def stop(self, timeout: float = 1.0) -> bool:
        """Pause the game simulation.

        This sets `self.status` to `Gamestatus.get('Paused')`. This method can also be spawned as a coroutine.
        A subsequent call of #GameStateMachine.run_game_loop() will resume the simulation at the point
        where it was stopped.

        # Arguments
        timeout (float): time in seconds to wait for the simulation to stop

        # Returns
        bool: wether or not the simulation was successfully stopped

        """
        return curio.run(self.stop, timeout)

    @awaitable(stop)
    async def stop(self, timeout: float = 1.0) -> bool:  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        if self._game_state_store.get_game_state().game_status == GameStatus.get("Active"):
            self._game_state_store.push_update(
                GameStateUpdate(
                    self._game_state_store.get_game_state().time_order + 1, game_status=GameStatus.get("Paused")
                )
            )
        t0 = time.time()
        while self._game_loop_is_running:
            if time.time() - t0 > timeout:
                break
            await curio.sleep(0)
        return not self._game_loop_is_running

    def time_step(self, game_state: GameState, dt: float) -> dict:
        """Calculate a game state update.

        This method should be implemented to return a dict with all the updated state attributes.

        # Arguments
        game_state (GameState): the state of the game prior to the time step
        dt (float): time in seconds since the last time step, use it to simulate at a consistent speed

        # Returns
        dict: updated game state attributes

        """
        raise NotImplementedError()
