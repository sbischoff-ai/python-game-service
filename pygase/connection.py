# -*- coding: utf-8 -*-
"""Provide low-level networking logic.

This module is not supposed to be required by users of this library.

# Contents
- #PROTOCOL_ID: 4 byte identifier for the PyGaSe package protocol
- #ProtocolIDMismatchError: exception for receiving non-PyGaSe packages
- #DuplicateSequenceError: exception for duplicate packages
- #Header: class for PyGaSe package headers
- #Package: class for PyGaSe UDP packages
- #ClientPackage: subclass of #Package for packages sent by clients
- #ServerPackage: subclass of #Package for packages sent by servers
- #ConnectionStatus: enum for the status of a client-server connection
- #Connection: class for the core network logic of client-server connections
- #ClientConnection: subclass of #Connection for the client side
- #ServerConnection: subclass of #Connectoin for the server side

"""

import time

import curio
from curio import socket
from curio.meta import awaitable, iscoroutinefunction

from pygase.utils import NamedEnum, Sqn, LockedRessource, Comparable, logger
from pygase.event import Event
from pygase.gamestate import GameState, GameStateUpdate

PROTOCOL_ID: bytes = bytes.fromhex("ffd0fab9")  # unique 4 byte identifier for pygase packages


class ProtocolIDMismatchError(ValueError):
    """Bytestring could not be identified as a valid PyGaSe package."""


class DuplicateSequenceError(ConnectionError):
    """Received a package with a sequence number that was already received before."""


class Header(Comparable):

    """Create a PyGaSe package header.

    # Arguments
    sequence (int): package sequence number
    ack (int): sequence number of the last received package
    ack_bitfield (str): A 32 character string representing the 32 sequence numbers prior to the last one received,
        with the first character corresponding the packge directly preceding it and so forth.
        '1' means that package has been received, '0' means it hasn't.

    # Attributes
    sequence (int): see corresponding constructor argument
    ack (int): see corresponding constructor argument
    ack_bitfield (str): see corresponding constructor argument

    ---
    Sequence numbers: A sequence of 0 means no packages have been sent or received.
    After 65535 sequence numbers wrap around to 1, so they can be stored in 2 bytes.

    """

    def __init__(self, sequence: int, ack: int, ack_bitfield: str):
        self.sequence = Sqn(sequence)
        self.ack = Sqn(ack)
        self.ack_bitfield = ack_bitfield

    def to_bytearray(self) -> bytearray:
        """Return 12 bytes representing the header."""
        result = bytearray(PROTOCOL_ID)
        result.extend(self.sequence.to_sqn_bytes())
        result.extend(self.ack.to_sqn_bytes())
        result.extend(int(self.ack_bitfield, 2).to_bytes(4, "big"))
        return result

    def destructure(self) -> tuple:
        """Return the tuple `(sequence, ack, ack_bitfield)`."""
        return (self.sequence, self.ack, self.ack_bitfield)

    @classmethod
    def deconstruct_datagram(cls, datagram: bytes) -> tuple:
        """Return a tuple containing the header and the rest of the datagram.

        # Arguments
        datagram (bytes): serialized PyGaSe package to deconstruct

        # Returns
        tuple: `(header, payload)` with `payload` being a bytestring of the rest of the datagram

        """
        if datagram[:4] != PROTOCOL_ID:
            raise ProtocolIDMismatchError
        sequence = Sqn.from_sqn_bytes(datagram[4:6])
        ack = Sqn.from_sqn_bytes(datagram[6:8])
        ack_bitfield = bin(int.from_bytes(datagram[8:12], "big"))[2:].zfill(32)
        payload = datagram[12:]
        return (cls(sequence, ack, ack_bitfield), payload)


class Package(Comparable):

    """Create a UDP package implementing the PyGaSe protocol.

    # Arguments
    header (Header): package header

    # Arguments
    events (pygase.event.Event): list events to attach to this package

    # Class Attributes
    timeout (float): time in seconds after which a package is considered to be lost, 1.0 by default
    max_size (int): maximum datagram size in bytes, 2048 by default

    # Attributes
    header (Header):

    # Members
    events (pygase.event.Event): see corresponding constructor argument

    ---
    PyGaSe servers and clients use the subclasses #ServerPackage and #ClientPackage respectively.
    The #Package class would also work on its own (it's not an 'abstract' class), in which case you would have
    all features of PyGaSe except for a synchronized game state.

    """

    timeout: float = 1.0  # package timeout in seconds
    max_size: int = 2048  # the maximum size of PyGaSe package in bytes

    def __init__(self, header: Header, events: list = None):
        self.header = header
        self._events = events if events is not None else []
        self._datagram: bytes = None

    @property
    def events(self) -> list:
        """Get a list of the events in the package."""
        return self._events.copy()

    def add_event(self, event: Event) -> None:
        """Add a PyGaSe event to the package.

        # Arguments
        event (pygase.event.Event): the event to be attached to this package

        # Raises
        OverflowError: if the package has previously been converted to a datagram and
           and its size with the added event would exceed #Package.max_size

        """
        if self._datagram is not None:
            bytepack = event.to_bytes()
            if len(self._datagram) + len(bytepack) + 2 > self.max_size:
                raise OverflowError("Package exceeds the maximum size of " + str(self.max_size) + " bytes.")
            self._datagram += len(bytepack).to_bytes(2, "big") + bytepack
        self._events.append(event)

    def get_bytesize(self) -> int:
        """Return the size in bytes the package has as a datagram."""
        if self._datagram is None:
            self._datagram = self.to_datagram()
        return len(self._datagram)

    def to_datagram(self) -> bytes:
        """Return package compactly serialized to `bytes`.

        # Raises
        OverflowError: if the resulting datagram would exceed #Package.max_size

        """
        if self._datagram is not None:
            return self._datagram
        datagram = self.header.to_bytearray()
        # The header makes up the first 12 bytes of the package
        datagram.extend(self._create_event_block())
        datagram = datagram
        if len(datagram) > self.max_size:
            raise OverflowError("Package exceeds the maximum size of " + str(self.max_size) + " bytes.")
        self._datagram = bytes(datagram)
        return self._datagram

    def _create_event_block(self) -> bytearray:
        event_block = bytearray()
        for event in self._events:
            bytepack = event.to_bytes()
            event_block.extend(len(bytepack).to_bytes(2, "big"))
            event_block.extend(bytepack)
        return event_block

    @classmethod
    def from_datagram(cls, datagram: bytes) -> "Package":
        """Deserialize datagram to #Package.

        # Arguments
        datagram (bytes): bytestring to deserialize, typically received via network

        # Returns
        Package: the deserialized package

        # Raises
        ProtocolIDMismatchError: if the first four bytes don't match the PyGaSe protocol ID

        """
        header, payload = Header.deconstruct_datagram(datagram)
        events = cls._read_out_event_block(payload)
        result = cls(header, events)
        result._datagram = datagram  # pylint: disable=protected-access
        return result

    @staticmethod
    def _read_out_event_block(event_block: bytes) -> list:
        events = []
        while event_block:
            bytesize = int.from_bytes(event_block[:2], "big")
            events.append(Event.from_bytes(event_block[2 : bytesize + 2]))
            event_block = event_block[bytesize + 2 :]
        return events


class ClientPackage(Package):

    """Subclass of #Package for packages sent by PyGaSe clients.

    # Arguments
    time_order (int): the clients last known time order of the game state

    # Attributes
    time_order (int): see corresponding constructor argument

    """

    def __init__(self, header: Header, time_order: int, events: list = None):
        super().__init__(header, events)
        self.time_order = Sqn(time_order)

    def to_datagram(self) -> bytes:
        """Override `Package.to_datagram` to include `time_order`."""
        if self._datagram is not None:
            return self._datagram
        datagram = self.header.to_bytearray()
        # The header makes up the first 12 bytes of the package
        datagram.extend(self.time_order.to_sqn_bytes())
        datagram.extend(self._create_event_block())
        datagram = datagram
        if len(datagram) > self.max_size:
            raise OverflowError("Package exceeds the maximum size of " + str(self.max_size) + " bytes.")
        self._datagram = bytes(datagram)
        return self._datagram

    @classmethod
    def from_datagram(cls, datagram: bytes) -> "ClientPackage":
        """Override #Package.from_datagram to include `time_order`."""
        header, payload = Header.deconstruct_datagram(datagram)
        time_order = Sqn.from_sqn_bytes(payload[:2])
        payload = payload[2:]
        events = cls._read_out_event_block(payload)
        result = cls(header, time_order, events)
        result._datagram = datagram  # pylint: disable=protected-access
        return result


class ServerPackage(Package):

    """Subclass of #Package for packages sent by PyGaSe servers.

    # Arguments
    game_state_update (pygase.gamestate.GameStateUpdate): the servers most recent minimal update for the client

    """

    def __init__(self, header: Header, game_state_update: GameStateUpdate, events: list = None):
        super().__init__(header, events)
        self.game_state_update = game_state_update

    def to_datagram(self) -> bytes:
        """Override #Package.to_datagram to include `game_state_update`."""
        if self._datagram is not None:
            return self._datagram
        datagram = self.header.to_bytearray()
        # The header makes up the first 12 bytes of the package
        state_update_bytepack = self.game_state_update.to_bytes()
        datagram.extend(len(state_update_bytepack).to_bytes(2, "big"))
        datagram.extend(state_update_bytepack)
        datagram.extend(self._create_event_block())
        datagram = datagram
        if len(datagram) > self.max_size:
            raise OverflowError("package exceeds the maximum size of " + str(self.max_size) + " bytes")
        self._datagram = bytes(datagram)
        return self._datagram

    @classmethod
    def from_datagram(cls, datagram: bytes) -> "ServerPackage":
        """Override #Package.from_datagram to include `game_state_update`."""
        header, payload = Header.deconstruct_datagram(datagram)
        state_update_bytesize = int.from_bytes(payload[:2], "big")
        game_state_update = GameStateUpdate.from_bytes(payload[2 : state_update_bytesize + 2])
        payload = payload[state_update_bytesize + 2 :]
        events = cls._read_out_event_block(payload)
        result = cls(header, game_state_update, events)
        result._datagram = datagram  # pylint: disable=protected-access
        return result


class ConnectionStatus(NamedEnum):

    """Enum for the state of a connection.

    - `'Disconnected'`
    - `'Connecting'`
    - `'Connected'`

    """


ConnectionStatus.register("Disconnected")
ConnectionStatus.register("Connected")
ConnectionStatus.register("Connecting")


class Connection:

    """Exchange packages between PyGaSe clients and servers.

    PyGaSe connections exchange events with their other side which are handled using custom handler functions.
    They also keep each other informed about which packages have been sent and received and automatically avoid
    network congestion.

    # Arguments
    remote_address (tuple): `('hostname', port)` for the connection partner's address
    event_handler (pygase.event.UniversalEventHandler): object that has a callable `handle` attribute that takes
        a #pygase.event.Event as argument
    event_wire (pygase.GameStateMachine): object to which events are to be repeated
        (has to implement a `_push_event` method)

    # Attributes
    remote_address (tuple): see corresponding constructor argument
    event_handler (pygase.event.UniversalEventHandler): see corresponding constructor argument
    event_wire (pygase.GameStateMachine): see corresponding constructor argument
    local_sequence (pygase.utils.Sqn): sequence number of the last sent package
    remote_sequence (pygase.utils.Sqn): sequence number of the last received package
    ack_bitfield (str): acks for the 32 packages prior to `self.remote_sequence`
    latency (float): the last registered RTT (round trip time)
    status (ConnectionStatus): an integer value that informs about the state of the connections
    quality (str): either `'good'` or `'bad'` depending on latency, used internally for
        congestion avoidance

    ---
    PyGaSe servers and clients use the subclasses #ServerConnection and #ClientConnection respectively.
    The #Connection class would also work on its own (it's not an 'abstract' class), in which case you would have
    all features of PyGaSe except for a synchronized game state.

    """

    timeout: float = 5.0  # connection timeout in seconds
    max_throttle_time: float = 60.0  # maximum time to wait before throttling
    min_throttle_time: float = 1.0  # minimum time to wait before throttling
    _package_intervals: dict = {
        "good": 1 / 40,
        "bad": 1 / 20,
    }  # maps connection.quality to time between sent packages in seconds
    _latency_threshold: float = 0.25  # latency that will trigger throttling

    def __init__(self, remote_address: tuple, event_handler, event_wire=None):
        logger.debug(f"Creating connection instance for remote address {remote_address}.")
        self.remote_address = remote_address
        self.event_handler = event_handler
        self.event_wire = event_wire
        self.local_sequence = Sqn(0)
        self.remote_sequence = Sqn(0)
        self.ack_bitfield = "0" * 32
        self.latency = 0.0
        self.status = ConnectionStatus.get("Disconnected")
        self.quality = "good"  # this is used for congestion avoidance
        self._package_interval = self._package_intervals["good"]
        self._outgoing_event_queue = curio.UniversalQueue()
        self._incoming_event_queue = curio.UniversalQueue()
        self._pending_acks: dict = {}
        self._event_callback_sequence = Sqn(0)
        self._events_with_callbacks: dict = {}
        self._event_callbacks: dict = {}
        self._last_recv = time.time()

    def _update_remote_info(self, received_sequence: Sqn):
        """Update `self.remote_sequence` and `self.ack_bitfield`."""
        if self.remote_sequence == 0:
            self.remote_sequence = received_sequence
            return
        sequence_diff = self.remote_sequence - received_sequence
        if sequence_diff < 0:
            self.remote_sequence = received_sequence
            if sequence_diff == -1:
                self.ack_bitfield = "1" + self.ack_bitfield[:-1]
            else:
                self.ack_bitfield = self.ack_bitfield[:sequence_diff].zfill(32)
        if sequence_diff == 0:
            raise DuplicateSequenceError
        if sequence_diff > 0:
            if self.ack_bitfield[sequence_diff - 1] == "1":
                raise DuplicateSequenceError
            self.ack_bitfield = self.ack_bitfield[: sequence_diff - 1] + "1" + self.ack_bitfield[sequence_diff:]

    async def _recv(self, package):
        """Handle a received package.

        Update `self.remote_sequence` and `self.ack_bitfield` based on `package`, resolve package loss
        and put the received events in the incoming event queue.

        # Raises
        DuplicateSequenceError: if a package with the same sequence has already been received

        """
        self._last_recv = time.time()
        if self.status != ConnectionStatus.get("Connected"):
            self._set_status("Connected")
        sequence, ack, ack_bitfield = package.header.destructure()
        logger.debug(f"Received package with sequence number {sequence} from {self.remote_address}.")
        self._update_remote_info(sequence)
        # resolve pending acks for sent packages (NEEDS REFACTORING)
        for pending_sequence in list(self._pending_acks):
            sequence_diff = ack - pending_sequence
            if sequence_diff == 0 or (0 < sequence_diff < 32 and ack_bitfield[sequence_diff - 1] == "1"):
                self._update_latency(time.time() - self._pending_acks[pending_sequence])
                if pending_sequence in self._events_with_callbacks:
                    for event_sequence in self._events_with_callbacks[pending_sequence]:
                        if self._event_callbacks[event_sequence]["ack"] is not None:
                            if iscoroutinefunction(self._event_callbacks[event_sequence]["ack"]):
                                await self._event_callbacks[event_sequence]["ack"]()
                            else:
                                self._event_callbacks[event_sequence]["ack"]()
                            del self._event_callbacks[event_sequence]
                    del self._events_with_callbacks[pending_sequence]
                del self._pending_acks[pending_sequence]
            elif time.time() - self._pending_acks[pending_sequence] > Package.timeout:
                if pending_sequence in self._events_with_callbacks:
                    for event_sequence in self._events_with_callbacks[pending_sequence]:
                        if self._event_callbacks[event_sequence]["timeout"] is not None:
                            if iscoroutinefunction(self._event_callbacks[event_sequence]["timeout"]):
                                await self._event_callbacks[event_sequence]["timeout"]()
                            else:
                                self._event_callbacks[event_sequence]["timeout"]()
                            del self._event_callbacks[event_sequence]
                    del self._events_with_callbacks[pending_sequence]
                del self._pending_acks[pending_sequence]
        for event in package.events:
            await self._incoming_event_queue.put(event)
            logger.debug(f"Received event of type {event.type} from {self.remote_address}.")
            if self.event_wire is not None:
                logger.debug("Pushing event to event wire.")
                await self.event_wire._push_event(event)  # pylint: disable=protected-access

    def dispatch_event(self, event: Event, ack_callback=None, timeout_callback=None):
        """Send an event to the connection partner.

        # Arguments
        event (pygase.event.Event): the event to dispatch
        ack_callback (callable, coroutine): will be executed after the event was received
        timeout_callback (callable, coroutine): will be executed if the event was not received

        ---
        Using long-running blocking operations in any of the callback functions can disturb the connection.

        """
        callback_sequence = 0
        if ack_callback is not None or timeout_callback is not None:
            self._event_callback_sequence += 1
            callback_sequence = self._event_callback_sequence
            self._event_callbacks[self._event_callback_sequence] = {"ack": ack_callback, "timeout": timeout_callback}
        self._outgoing_event_queue.put((event, callback_sequence))
        logger.debug(f"Dispatched event of type {event.type} to be sent to {self.remote_address}.")

    async def _handle_next_event(self):
        """Handle an event from the incoming event queue.

        This coroutine returns once the handler has finished.

        """
        event = await self._incoming_event_queue.get()
        if self.event_handler.has_event_type(event.type):
            await self.event_handler.handle(event)
        await self._incoming_event_queue.task_done()

    async def _event_loop(self):
        """Continously handle incoming events.

        This coroutine, once spawned, will keep handling events until it is explicitly cancelled.

        """
        logger.debug(f"Starting event loop for connection to {self.remote_address}.")
        while True:
            try:
                await self._handle_next_event()
            except curio.CancelledError:
                break
        logger.debug(f"Stopped handling events from {self.remote_address}.")

    async def _send_loop(self, sock):
        """Continously send packages to the connection partner.

        This coroutine, once spawned, will keep sending packages to the remote_address until it is explicitly
        cancelled or the connection times out.

        # Arguments
        sock (curio.io.Socket): socket via which to send the packages

        """
        logger.debug(f"Starting to send packages to {self.remote_address} every {self._package_interval} seconds.")
        congestion_avoidance_task = await curio.spawn(self._congestion_avoidance_monitor)
        while True:
            try:
                t0 = time.time()
                if t0 - self._last_recv > self.timeout:
                    logger.warning(f"Connection to {self.remote_address} timed out after {self.timeout} seconds.")
                    self._set_status("Disconnected")
                    break
                await self._send_next_package(sock)
                await curio.sleep(max([self._package_interval - time.time() + t0, 0]))
            except curio.CancelledError:
                break
        logger.debug(f"Stopped sending packages to {self.remote_address}.")
        await congestion_avoidance_task.cancel()

    def _create_next_package(self):
        """Create a package with the correct header to send next."""
        return Package(Header(self.local_sequence, self.remote_sequence, self.ack_bitfield))

    async def _send_next_package(self, sock):
        """Send a package with up to 5 events.

        This coroutine returns once the package is sent.

        # Arguments
        sock (curio.io.Socket): socket via which to send the package

        """
        self.local_sequence += 1
        package = self._create_next_package()
        while len(package.events) < 5 and not self._outgoing_event_queue.empty():
            event, callback_sequence = await self._outgoing_event_queue.get()
            if callback_sequence != 0:
                if self.local_sequence not in self._events_with_callbacks:
                    self._events_with_callbacks[self.local_sequence] = [callback_sequence]
                else:
                    self._events_with_callbacks[self.local_sequence].append(callback_sequence)
            logger.debug(
                (
                    f"Sending event of type {event.type} to {self.remote_address}."
                    f"event data: handler_args = {event.handler_args}, handler_kwargs = {event.handler_kwargs}"
                )
            )
            package.add_event(event)
            await self._outgoing_event_queue.task_done()
        await sock.sendto(package.to_datagram(), self.remote_address)
        logger.debug(f"Sent package with sequence number {package.header.sequence} to {self.remote_address}.")
        self._pending_acks[package.header.sequence] = time.time()

    def _set_status(self, status: str):
        """Set `self.status` to a new #ConnectionStatus value."""
        self.status = ConnectionStatus.get(status)
        logger.info(f"Status of connection to {self.remote_address} set to '{status}'.")

    def _update_latency(self, rtt: int):
        """Update `self.latency` according to a measured rount trip time.

        Network jitter is filtered through a moving exponential average.

        """
        self.latency += 0.1 * (rtt - self.latency)

    async def _congestion_avoidance_monitor(self):
        """Continously monitor connection quality and throttle if needed.

        This coroutine will keep adjusting `self.quality` and throttling the rate at which packages are sent
        until it is explicitly cancelled.

        """
        state = {
            "throttle_time": self.min_throttle_time,
            "last_quality_change": time.time(),
            "last_good_quality_milestone": time.time(),
        }
        logger.debug(f"Starting congestion avoidance for connection to {self.remote_address}.")
        while True:
            try:
                self._throttling_state_machine(time.time(), state)
                await curio.sleep(Connection.min_throttle_time / 2.0)
            except curio.CancelledError:
                break
        logger.debug(f"Stopped congestion avoidance for connection to {self.remote_address}.")

    def _throttling_state_machine(self, t: int, state: dict):
        """Calculate a new state for congestion avoidance."""
        if self.quality == "good":
            if self.latency > self._latency_threshold:  # switch to bad mode
                logger.warning(
                    (
                        f"Throttling down connection to {self.remote_address} because "
                        "latency ({self.latency}) is above latency threshold ({self._latency_threshold})."
                    )
                )
                self.quality = "bad"
                self._package_interval = self._package_intervals["bad"]
                logger.debug(f"new package interval: {self._package_interval} seconds.")
                # if good conditions didn't last at least the throttle time, increase it
                if t - state["last_quality_change"] < state["throttle_time"]:
                    state["throttle_time"] = min([state["throttle_time"] * 2.0, self.max_throttle_time])
                state["last_quality_change"] = t
            # if good conditions lasted throttle time since last milestone
            elif t - state["last_good_quality_milestone"] > state["throttle_time"]:
                if self._package_interval > self._package_intervals["good"]:
                    logger.info(
                        (
                            f"Throttling up connection to {self.remote_address} because latency ({self.latency}) "
                            f"has been below latency threshold ({self._latency_threshold}) "
                            f"for {state['throttle_time']} seconds."
                        )
                    )
                    self._package_interval = self._package_intervals["good"]
                    logger.debug(f"new package interval: {self._package_interval} seconds.")
                state["throttle_time"] = max([state["throttle_time"] / 2.0, self.min_throttle_time])
                state["last_good_quality_milestone"] = t
        else:  # self.quality == 'bad'
            if self.latency < self._latency_threshold:  # switch to good mode
                self.quality = "good"
                state["last_quality_change"] = t
                state["last_good_quality_milestone"] = t


class ClientConnection(Connection):

    """Subclass of #Connection to describe the client side of a PyGaSe connection.

    Client connections hold a copy of the game state which is continously being updated according to
    state updates received from the server.

    # Attributes
    game_state_context (pygase.utils.LockedRessource): provides thread-safe access to a #pygase.GameState

    """

    def __init__(self, remote_address: tuple, event_handler):
        super().__init__(remote_address, event_handler)
        self._command_queue = curio.UniversalQueue()
        self.game_state_context = LockedRessource(GameState())

    def shutdown(self, shutdown_server: bool = False):
        """Shut down the client connection.

        This method can also be spawned as a coroutine.

        # Arguments
        shutdown_server (bool): wether or not the server should be shut down too
            (only has an effect if the client has host permissions)

        """
        curio.run(self.shutdown, shutdown_server)

    @awaitable(shutdown)
    async def shutdown(self, shutdown_server: bool = False):  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        if shutdown_server:
            await self._command_queue.put("shutdown")
        else:
            await self._command_queue.put("shut_me_down")
        logger.debug(
            (
                f"Dispatched shutdown command with shutdown_server={shutdown_server} "
                f"for connection to {self.remote_address}."
            )
        )

    def _create_next_package(self):
        """Override #Connection._create_next_package to send a #ClientPackage."""
        time_order = self.game_state_context.ressource.time_order
        return ClientPackage(Header(self.local_sequence, self.remote_sequence, self.ack_bitfield), time_order)

    def loop(self):
        """Continously operate the connection.

        This method will keep sending and receiving packages and handling events until it is cancelled or
        the connection receives a shutdown command. It can also be spawned as a coroutine.

        """
        curio.run(self.loop)

    @awaitable(loop)
    async def loop(self):  # pylint: disable=function-redefined
        # pylint: disable=missing-docstring
        logger.info(f"Trying to connect to server ...")
        self._set_status("Connecting")
        async with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            send_loop_task = await curio.spawn(self._send_loop, sock)
            recv_loop_task = await curio.spawn(self._client_recv_loop, sock)
            event_loop_task = await curio.spawn(self._event_loop)
            # check for disconnect event
            while not self.status == ConnectionStatus.get("Disconnected"):
                command = await self._command_queue.get()
                if command == "shutdown":
                    logger.info(f"Sending shutdown command to server at {self.remote_address}.")
                    await sock.sendto("shutdown".encode("utf-8"), self.remote_address)
                    break
                elif command == "shut_me_down":
                    break
            logger.info(f"Shutting down connection to {self.remote_address}.")
            await recv_loop_task.cancel()
            await send_loop_task.cancel()
            await event_loop_task.cancel()
            self._set_status("Disconnected")

    async def _recv(self, package: ServerPackage):
        """Extend #Connection._recv to update the game state."""
        await super()._recv(package)
        async with curio.abide(self.game_state_context.lock):
            logger.debug(
                (
                    f"Updating game state from time order "
                    f"{self.game_state_context.ressource.time_order} to "
                    f"{package.game_state_update.time_order}."
                )
            )
            self.game_state_context.ressource += package.game_state_update

    async def _client_recv_loop(self, sock):
        """Continously handle packages received from the server.

        This coroutine, once spawned, will keep receiving packages from the server until it is explicitly
        cancelled.

        # Arguments
        sock (curio.io.Socket): socket with which to receive server packages

        """
        while self.local_sequence == 0:
            await curio.sleep(0)
        logger.debug(f"Starting to listen to packages from server at {self.remote_address}.")
        while True:
            try:
                data = await sock.recv(ServerPackage.max_size)
                package = ServerPackage.from_datagram(data)
                await self._recv(package)
            except curio.CancelledError:
                break
        logger.debug(f"Stopped receiving packages from {self.remote_address}.")


class ServerConnection(Connection):

    """Subclass of #Connection that describes the server side of a PyGaSe connection.

    # Arguments
    game_state_store (pygase.GameStateStore): object that serves as an interface to the game state repository
        (has to provide the methods `get_gamestate`, `get_update_cache` and `push_update`)
    last_client_time_order (pygase.utils.Sqn): the last time order number known to the client

    # Attributes
    game_state_store (pygase.GameStateStore): see corresponding constructor argument
    last_client_time_order (pygase.utils.Sqn): see corresponding constructor argument

    """

    def __init__(
        self, remote_address: tuple, event_handler, game_state_store, last_client_time_order: Sqn, event_wire=None
    ):
        super().__init__(remote_address, event_handler, event_wire)
        self.game_state_store = game_state_store
        self.last_client_time_order = last_client_time_order

    def _create_next_package(self):
        """Override #Connection._create_next_package to include game state updates."""
        update_cache = self.game_state_store.get_update_cache()
        # Respond by sending the sum of all updates since the client's time-order point.
        # Or the whole game state if the client doesn't have it yet.
        if self.last_client_time_order == 0:
            logger.debug(f"Sending full game state to client {self.remote_address}.")
            game_state = self.game_state_store.get_game_state()
            update = GameStateUpdate(**game_state.__dict__)
        else:
            update_base = GameStateUpdate(self.last_client_time_order)
            update = sum((upd for upd in update_cache if upd > update_base), update_base)
            logger.debug(
                (
                    f"Sending update from time order {self.last_client_time_order} "
                    f"to {update.time_order} to client {self.remote_address}."
                )
            )
        return ServerPackage(Header(self.local_sequence, self.remote_sequence, self.ack_bitfield), update)

    async def _recv(self, package: ClientPackage):
        """Extend #Connection._recv to update `self.last_client_time_order`."""
        await super()._recv(package)
        self.last_client_time_order = package.time_order

    @classmethod
    async def loop(cls, hostname: str, port: int, server, event_wire) -> None:
        """Continously orchestrate and operate connections to clients.

        This coroutine will keep listening for client packages, create new #ServerConnection objects
        when necessary and make sure all packages are handled by and sent via the right connection.

        It will return as soon as the server receives a shutdown message.

        # Arguments
        hostname (str): the hostname or IPv4 address to which to bind the server socket
        port (int): the port number to which to bind the server socket
        server (pygase.Server): the server for which this loop is run
        event_wire (pygase.GameStateMachine): object to which events are to be repeated
           (has to implement a `_push_event` method)

        """
        logger.info(f"Trying to run server on {(hostname, port)} ...")
        async with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((hostname, port))
            server._hostname, server._port = sock.getsockname()  # pylint: disable=protected-access
            connection_tasks = curio.TaskGroup()
            logger.info(f"Server successfully started and listening to packages from clients on {(hostname, port)}.")
            while True:
                data, client_address = await sock.recvfrom(Package.max_size)
                try:
                    package = ClientPackage.from_datagram(data)
                    # Create new connection if client is unknown.
                    if not client_address in server.connections:
                        logger.info(f"New client connection from {client_address}.")
                        new_connection = cls(
                            client_address,
                            server._universal_event_handler,  # pylint: disable=protected-access
                            server.game_state_store,
                            package.time_order,
                            event_wire,
                        )
                        await connection_tasks.spawn(
                            new_connection._send_loop, sock  # pylint: disable=protected-access
                        )
                        await connection_tasks.spawn(new_connection._event_loop)  # pylint: disable=protected-access
                        # For now, the first client connection becomes host.
                        if server.host_client is None:
                            logger.info(f"Setting {client_address} as client with host permissions.")
                            server.host_client = client_address
                        server.connections[client_address] = new_connection
                    elif server.connections[client_address].status == ConnectionStatus.get("Disconnected"):
                        # Start sending packages again, which will also set status to "Connected".
                        logger.info(f"Client reconnecting from {client_address}.")
                        await connection_tasks.spawn(
                            server.connections[client_address]._send_loop, sock  # pylint: disable=protected-access
                        )
                    await server.connections[client_address]._recv(package)  # pylint: disable=protected-access
                except ProtocolIDMismatchError:
                    # ignore all non-PyGaSe packages
                    try:
                        if data.decode("utf-8") == "shutdown" and client_address == server.host_client:
                            logger.info(f"Received shutdown command from host client {client_address}.")
                            break
                        elif data.decode("utf-8") == "shut_me_down":
                            break
                        else:
                            logger.warning("Received unknown package.")
                    except UnicodeDecodeError:
                        logger.warning("Received unknown package.")
            logger.info(f"Shutting down server on {(hostname, port)}.")
            await connection_tasks.cancel_remaining()
