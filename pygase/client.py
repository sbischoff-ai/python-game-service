# -*- coding: utf-8 -*-
"""Connect to PyGaSe servers.

### Contents
 - *Client*: user interface class for PyGaSe clients

"""

import threading

import curio
from curio.meta import awaitable

from pygase.connection import ClientConnection
from pygase.event import UniversalEventHandler, Event


class Client:

    """Exchange events with a PyGaSe server and access a synchronized game state.

    #### Attributes
    - `connection`: `ClientConnection` object that contains all networking information

    """

    def __init__(self):
        self.connection = None
        self._universal_event_handler = UniversalEventHandler()

    def connect(self, port: int, hostname: str = "localhost") -> None:
        """Open a connection to a PyGaSe server.

        This is a blocking function but can also be spawned as a coroutine or in a thread via `connect_in_thread`.

        #### Arguments
        - `port`: port number of the server to which to connect

        #### Optional Arguments
        - `hostname`: hostname of the server to which to connect

        """
        self.connection = ClientConnection((hostname, port), self._universal_event_handler)
        curio.run(self.connection.loop)

    @awaitable(connect)
    async def connect(self, port: int, hostname: str = "localhost") -> None:  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        self.connection = ClientConnection((hostname, port), self._universal_event_handler)
        await self.connection.loop()

    def connect_in_thread(self, port: int, hostname: str = "localhost") -> threading.Thread:
        """Open a connection in a seperate thread.

        See `Client.connect(port, hostname)`.

        #### Returns
        the thread the client loop runs in

        """
        self.connection = ClientConnection((hostname, port), self._universal_event_handler)
        thread = threading.Thread(target=curio.run, args=(self.connection.loop,))
        thread.start()
        return thread

    def disconnect(self, shutdown_server: bool = False) -> None:
        """Close the client connection.

        This method can also be spawned as a coroutine.

        #### Optional Arguments
        - `shutdown_server`: wether or not the server should be shut down
            (only has an effect if the client has host permissions)

        """
        self.connection.shutdown(shutdown_server)

    @awaitable(disconnect)
    async def disconnect(self, shutdown_server: bool = False) -> None:  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        await self.connection.shutdown(shutdown_server)

    def access_game_state(self):
        """Return a context manager to access the shared game state.

        Can be used in a `with` block to lock the synchronized game_state while working with it.

        Example:
        ```python
        with client.access_game_state() as game_state:
            do_stuff(game_state)
        ```

        """
        return self.connection.game_state_context

    def dispatch_event(self, event_type: str, *args, retries: int = 0, ack_callback=None, **kwargs) -> None:
        """Send an event to the server.

        #### Arguments
        - `event_type`: event type identifier that links to a handler

        #### Optional Arguments
        Additional positional arguments represent event data and will be passed to the servers handler function.

        #### Keyword Arguments
        - `retries`: number of times the event is to be resent in case it times out
        - `ack_callback`: function or coroutine to be executed after the event was received
        Additional keyword arguments will be sent as event data and passed to the handler function.

        """
        event = Event(event_type, *args, **kwargs)
        timeout_callback = None
        if retries > 0:
            timeout_callback = lambda: self.dispatch_event(
                event_type, *args, retries=retries - 1, ack_callback=ack_callback, **kwargs
            )
        self.connection.dispatch_event(event, ack_callback, timeout_callback)

    def register_event_handler(self, event_type: str, event_handler_function) -> None:
        """Register an event handler for a specific event type.

        #### Arguments
        - `event_type`: event type to link the handler function to
        - `handler_func`: function or coroutine to be invoked for events of the given type

        """
        self._universal_event_handler.register_event_handler(event_type, event_handler_function)
