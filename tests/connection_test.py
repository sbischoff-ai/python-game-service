import time

import pytest
from freezegun import freeze_time
import curio
from curio import socket

from pygase.utils import Sqn
from pygase.event import Event
from pygase.gamestate import GameStateUpdate
from pygase.connection import (
    Header,
    Package,
    ClientPackage,
    ServerPackage,
    Connection,
    DuplicateSequenceError,
    ProtocolIDMismatchError,
)


class TestPackage:
    def test_bytepacking(self):
        package = Package(Header(4, 5, "10" * 16), [Event("TEST", "Foo", "Bar")])
        datagram = package.to_datagram()
        unpacked_package = Package.from_datagram(datagram)
        assert package == unpacked_package

    def test_protocol_ID_check(self):
        package = Package(Header(1, 2, "0" * 32))
        datagram = package.to_datagram()
        datagram = datagram[1:]
        with pytest.raises(ProtocolIDMismatchError):
            Package.from_datagram(datagram)

    def test_size_restriction(self):
        with pytest.raises(OverflowError) as error:
            Package(Header(1, 4, "0" * 32), [Event("TEST", bytes(2048 - 13))]).to_datagram()
        assert str(error.value) == "Package exceeds the maximum size of 2048 bytes."

    def test_add_event(self):
        package = Package(Header(1, 2, "0" * 32))
        event1 = Event("TEST", 1, 2, 3)
        event2 = Event("FOO", "Bar")
        package.add_event(event1)
        package.add_event(event2)
        assert len(package.events) == 2
        assert event1 in package.events and event2 in package.events
        with pytest.raises(OverflowError):
            package.get_bytesize()
            package.add_event(Event("BIG", bytes(2030)))


class TestClientPackage:
    def test_bytepacking(self):
        package = ClientPackage(Header(4, 5, "10" * 16), 1, [Event("TEST", "Foo", "Bar")])
        datagram = package.to_datagram()
        unpacked_package = ClientPackage.from_datagram(datagram)
        assert package == unpacked_package


class TestServerPackage:
    def test_bytepacking(self):
        package = ServerPackage(Header(4, 5, "10" * 16), GameStateUpdate(2), [Event("TEST", "Foo", "Bar")])
        datagram = package.to_datagram()
        unpacked_package = ServerPackage.from_datagram(datagram)
        assert package == unpacked_package


class TestConnection:
    def test_recv_first_package(self):
        connection = Connection(("host", 1234), None)
        assert connection.local_sequence == 0
        assert connection.remote_sequence == 0
        assert connection.ack_bitfield == "0" * 32
        curio.run(connection._recv, Package(Header(sequence=1, ack=0, ack_bitfield="0" * 32)))
        assert connection.local_sequence == 0
        assert connection.remote_sequence == 1
        assert connection.ack_bitfield == "0" * 32

    def test_recv_second_package(self):
        connection = Connection(("host", 1234), None)
        connection.remote_sequence = Sqn(1)
        connection.ack_bitfield = "0" * 32
        curio.run(connection._recv, Package(Header(sequence=2, ack=1, ack_bitfield="0" * 32)))
        assert connection.remote_sequence == 2
        assert connection.ack_bitfield == "1" + "0" * 31

    def test_recv_second_package_comes_first(self):
        connection = Connection(("host", 1234), None)
        assert connection.remote_sequence == 0
        assert connection.ack_bitfield == "0" * 32
        curio.run(connection._recv, Package(Header(sequence=2, ack=0, ack_bitfield="0" * 32)))
        assert connection.remote_sequence == 2
        assert connection.ack_bitfield == "0" * 32

    def test_recv_first_package_comes_second(self):
        connection = Connection(("host", 1234), None)
        connection.remote_sequence = Sqn(2)
        connection.ack_bitfield = "0" * 32
        curio.run(connection._recv, Package(Header(sequence=1, ack=1, ack_bitfield="0" * 32)))
        assert connection.remote_sequence == 2
        assert connection.ack_bitfield == "1" + "0" * 31

    def test_recv_three_packages_arrive_out_of_sequence(self):
        connection = Connection(("host", 1234), None)
        connection.remote_sequence = Sqn(100)
        connection.ack_bitfield = "0110" + "1" * 28
        curio.run(connection._recv, Package(Header(sequence=101, ack=100, ack_bitfield="1" * 32)))
        assert connection.remote_sequence == 101
        assert connection.ack_bitfield == "10110" + "1" * 27
        curio.run(connection._recv, Package(Header(sequence=99, ack=100, ack_bitfield="1" * 32)))
        assert connection.remote_sequence == 101
        assert connection.ack_bitfield == "11110" + "1" * 27
        curio.run(connection._recv, Package(Header(sequence=96, ack=101, ack_bitfield="1" * 32)))
        assert connection.remote_sequence == 101
        assert connection.ack_bitfield == "1" * 32

    def test_recv_duplicate_package_in_sequence(self):
        connection = Connection(("host", 1234), None)
        connection.remote_sequence = Sqn(500)
        connection.ack_bitfield = "1" * 32
        curio.run(connection._recv, Package(Header(sequence=501, ack=500, ack_bitfield="1" * 32)))
        with pytest.raises(DuplicateSequenceError):
            curio.run(connection._recv(Package(Header(sequence=501, ack=500, ack_bitfield="1" * 32))))

    def test_recv_duplicate_package_out_of_sequence(self):
        connection = Connection(("host", 1234), None)
        connection.remote_sequence = Sqn(1000)
        connection.ack_bitfield = "1" * 32
        with pytest.raises(DuplicateSequenceError):
            curio.run(connection._recv, Package(Header(sequence=990, ack=500, ack_bitfield="1" * 32)))

    def test_congestion_avoidance(self):
        connection = Connection(("", 1234), None)
        state = {
            "throttle_time": Connection._min_throttle_time,
            "last_quality_change": 0.0,
            "last_good_quality_milestone": 0.0,
        }
        assert connection.quality == "good"
        assert connection.latency == 0.0
        assert connection._package_interval == Connection._package_intervals["good"]
        t = Connection._min_throttle_time
        connection._throttling_state_machine(t, state)
        assert connection.quality == "good"
        assert connection._package_interval == Connection._package_intervals["good"]
        connection.latency = Connection._latency_threshold + 0.01
        t += Connection._min_throttle_time
        connection._throttling_state_machine(t, state)
        assert connection.quality == "bad"
        assert connection._package_interval == Connection._package_intervals["bad"]
        assert state["throttle_time"] == Connection._min_throttle_time
        connection.latency = Connection._latency_threshold - 0.01
        t += Connection._min_throttle_time / 2.0
        connection._throttling_state_machine(t, state)
        assert connection.quality == "good"
        assert connection._package_interval == Connection._package_intervals["bad"]
        assert state["throttle_time"] == Connection._min_throttle_time
        t += 1.1 * Connection._min_throttle_time
        connection._throttling_state_machine(t, state)
        assert connection.quality == "good"
        assert connection._package_interval == Connection._package_intervals["good"]
        assert state["throttle_time"] == Connection._min_throttle_time
        connection.latency = Connection._latency_threshold + 0.01
        t += Connection._min_throttle_time / 2.0
        connection._throttling_state_machine(t, state)
        connection.latency = Connection._latency_threshold - 0.01
        t += Connection._min_throttle_time / 2.0
        connection._throttling_state_machine(t, state)
        connection.latency = Connection._latency_threshold + 0.01
        t += Connection._min_throttle_time / 2.0
        connection._throttling_state_machine(t, state)
        assert connection.quality == "bad"
        assert connection._package_interval == Connection._package_intervals["bad"]
        assert state["throttle_time"] == 2.0 * Connection._min_throttle_time
        connection.latency = Connection._latency_threshold - 0.01
        t += Connection._min_throttle_time / 2.0
        connection._throttling_state_machine(t, state)
        t += 2.1 * Connection._min_throttle_time
        connection._throttling_state_machine(t, state)
        assert connection.quality == "good"
        assert connection._package_interval == Connection._package_intervals["good"]
        assert state["throttle_time"] == Connection._min_throttle_time

    def test_send_package(self):
        send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_socket.bind(("localhost", 0))
        connection = Connection(recv_socket.getsockname(), None)
        assert connection.local_sequence == 0
        curio.run(connection._send_next_package, send_socket)
        data = curio.run(recv_socket.recv, Package._max_size)
        package = Package.from_datagram(data)
        assert package.header.sequence == 1 and connection.local_sequence == 1
        assert package.header.ack == 0 and package.header.ack_bitfield == "0" * 32
        curio.run(connection._send_next_package, send_socket)
        data = curio.run(recv_socket.recv, Package._max_size)
        package = Package.from_datagram(data)
        assert package.header.sequence == 2 and connection.local_sequence == 2
        assert package.header.ack == 0 and package.header.ack_bitfield == "0" * 32
        connection.local_sequence = Sqn.get_max_sequence()
        curio.run(connection._send_next_package, send_socket)
        data = curio.run(recv_socket.recv, Package._max_size)
        package = Package.from_datagram(data)
        assert package.header.sequence == 1 and connection.local_sequence == 1
        assert package.header.ack == 0 and package.header.ack_bitfield == "0" * 32
        curio.run(send_socket.close)
        curio.run(recv_socket.close)

    def test_resolve_acks(self):
        async def sendto(*args):
            pass

        sock = type("socket", (), {"sendto": sendto})()
        connection = Connection(("", 0), None)
        curio.run(connection._send_next_package, sock)
        assert connection._pending_acks.keys() == {1}
        assert connection.latency == 0
        curio.run(connection._recv, Package(Header(1, 0, "0" * 32)))
        assert connection._pending_acks
        curio.run(connection._recv, Package(Header(2, 1, "0" * 32)))
        assert not connection._pending_acks
        assert connection.latency > 0
        for _ in range(1, 5):
            curio.run(connection._send_next_package, sock)
        assert connection._pending_acks.keys() == {2, 3, 4, 5}
        curio.run(connection._recv, Package(Header(3, 4, "01" + "0" * 30)))
        assert connection._pending_acks.keys() == {3, 5}

    def test_package_timeout(self):
        async def sendto(*args):
            pass

        sock = type("socket", (), {"sendto": sendto})()
        connection = Connection(("", 0), None)
        with freeze_time("2012-01-14 12:00:01") as frozen_time:
            curio.run(connection._send_next_package, sock)
            assert connection._pending_acks.keys() == {1}
            frozen_time.tick()
            frozen_time.tick()
            curio.run(connection._recv, Package(Header(1, 0, "0" * 32)))
            assert not connection._pending_acks
            assert connection.latency == 0

    def test_dispatch_event(self):
        send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_socket.bind(("localhost", 0))
        connection = Connection(recv_socket.getsockname(), None)
        event = Event("TEST", 1, 2, 3, 4)
        connection.dispatch_event(event)
        curio.run(connection._send_next_package, send_socket)
        data = curio.run(recv_socket.recv, Package._max_size)
        package = Package.from_datagram(data)
        assert package.events == [event]
        curio.run(connection._send_next_package, send_socket)
        data = curio.run(recv_socket.recv, Package._max_size)
        package = Package.from_datagram(data)
        assert package.events == []

    def test_dispatch_multiple_events(self):
        send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_socket.bind(("localhost", 0))
        connection = Connection(recv_socket.getsockname(), None)
        event = Event("TEST", 1, 2, 3, 4)
        another_event = Event("TEST", 3, 4, 5, 6)
        connection.dispatch_event(event)
        connection.dispatch_event(another_event)
        curio.run(connection._send_next_package, send_socket)
        data = curio.run(recv_socket.recv, Package._max_size)
        package = Package.from_datagram(data)
        assert package.events == [event, another_event]

    def test_receive_events(self):
        class EventHandler:
            call_count = 0

            def __init__(self):
                self.events = []

            async def handle(self, event, **kwargs):
                EventHandler.call_count += 1
                self.events.append(event)

            def has_event_type(self, event_type):
                return True

        event_handler = EventHandler()
        connection = Connection(("", 0), event_handler)
        assert connection.event_handler == event_handler
        event = Event("TEST", 1, 2, 3, 4)
        package = Package(Header(1, 1, "1" * 32), [event, event])
        assert package.events == [event, event]
        assert connection.remote_sequence == 0
        curio.run(connection._recv, package)
        assert not connection._incoming_event_queue.empty()
        assert EventHandler.call_count == 0
        curio.run(connection._handle_next_event)
        assert EventHandler.call_count == 1
        assert not connection._incoming_event_queue.empty()
        assert event_handler.events == [event]
        curio.run(connection._handle_next_event)
        assert EventHandler.call_count == 2
        assert connection._incoming_event_queue.empty()
        assert event_handler.events == [event, event]

    def test_event_ack_callbacks(self):
        async def sendto(*args):
            pass

        sock = type("socket", (), {"sendto": sendto})()

        class callback:
            count = 0

            def __init__(self):
                callback.count += 1

        connection = Connection(("", 0), None)
        event = Event("TEST")
        connection.dispatch_event(event, ack_callback=callback)
        curio.run(connection._send_next_package, sock)
        curio.run(connection._recv, Package(Header(1, 1, "0" * 32)))
        assert callback.count == 1
        curio.run(connection._recv, Package(Header(2, 1, "0" * 32)))
        assert callback.count == 1
        connection.dispatch_event(event, ack_callback=callback)
        connection.dispatch_event(event)
        connection.dispatch_event(event, ack_callback=callback)
        curio.run(connection._send_next_package, sock)
        assert connection.local_sequence == 2
        curio.run(connection._recv, Package(Header(3, 2, "1" + "0" * 31)))
        assert callback.count == 3

    def test_event_timeout_calbacks(self):
        async def sendto(*args):
            pass

        sock = type("socket", (), {"sendto": sendto})()

        class callback:
            count = 0

            def __init__(self):
                callback.count += 1

        with freeze_time("2012-01-14 12:00:01") as frozen_time:
            connection = Connection(("", 0), None)
            event = Event("TEST")
            connection.dispatch_event(event, timeout_callback=callback)
            curio.run(connection._send_next_package, sock)
            curio.run(connection._recv, Package(Header(1, 1, "0" * 32)))
            assert callback.count == 0
            frozen_time.tick()
            frozen_time.tick()
            curio.run(connection._recv, Package(Header(2, 1, "0" * 32)))
            assert callback.count == 0
            connection.dispatch_event(event, timeout_callback=callback)
            curio.run(connection._send_next_package, sock)
            frozen_time.tick()
            frozen_time.tick()
            curio.run(connection._recv, Package(Header(3, 1, "0" * 32)))
            assert callback.count == 1
