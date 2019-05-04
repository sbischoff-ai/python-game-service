# -*- coding: utf-8 -*-
"""Handle events in PyGaSe clients, servers and state machines.

Contains the basic components of the PyGaSe event framework.

### Contents
- #Event: class for serializable event objects with event type and data
- #UniversalEventHandler: class for components that can handle various event types

"""

from curio.meta import iscoroutinefunction

from pygase.utils import Sendable, logger


class Event(Sendable):

    """Send PyGaSe events and attached data via UDP packages.

    # Arguments
    event_type (str): string that identifies the event and links it to a handler

    # Arguments
    Additional positional arguments represent event data and will be passed to the handler function
    on the other side of the connection.
    keyword arguments to be passed to the handler function on the other side of the connection

    # Attributes
    type (str):
    handler_args (list):
    handler_kwargs (dict):

    """

    def __init__(self, event_type: str, *args, **kwargs):
        self.type: str = event_type
        self.handler_args: list = list(args)
        self.handler_kwargs: dict = kwargs


class UniversalEventHandler:

    """Handle PyGaSe events with callback functions."""

    def __init__(self):
        self._event_handlers = {}

    # additional type checking for handler function
    def register_event_handler(self, event_type: str, event_handler_function) -> None:
        """Register an event handler for a specific event type.

        # Arguments
        event_type (str): string that identifies the events to be handled by this function
        event_handler_function (callable, coroutine): callback function or coroutine that will be invoked
        with the handler args and kwargs with which the incoming event has been dispatched

        """
        logger.info(f"Registering event handler for events of type {event_type}.")
        if not callable(event_handler_function):
            raise TypeError(f"'{event_handler_function.__class__.__name__}' object is not callable.")
        self._event_handlers[event_type] = event_handler_function

    async def handle(self, event: Event, **kwargs):
        """Asynchronously invoke the appropriate handler function.

        This method is a coroutine and must be `await`ed.

        # Arguments
        event (Event): the event to be handled
        keyword arguments to be passed to the handler function (in addition to those already attached to the event)

        """
        logger.debug(
            (f"Handling {event.type} event with args={event.handler_args} and kwargs={event.handler_kwargs}.")
        )
        if iscoroutinefunction(self._event_handlers[event.type]):
            return await self._event_handlers[event.type](*event.handler_args, **dict(event.handler_kwargs, **kwargs))
        return self._event_handlers[event.type](*event.handler_args, **dict(event.handler_kwargs, **kwargs))

    def has_event_type(self, event_type: str) -> bool:
        """Check if a handler was registered for `event_type`."""
        return event_type in self._event_handlers
