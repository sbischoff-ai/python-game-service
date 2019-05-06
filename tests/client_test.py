# -*- coding: utf-8 -*-

import threading
import queue

import pytest
from freezegun import freeze_time

from pygase.client import Client
from pygase.event import UniversalEventHandler
from pygase.connection import ClientConnection
from pygase.gamestate import GameState


class TestClient:
    def test_instatiation(self):
        client = Client()
        assert client.connection == None
        assert client._universal_event_handler.__class__ == UniversalEventHandler

    def test_game_state_access(self):
        client = Client()
        client.connection = ClientConnection(None, None)
        with client.access_game_state() as game_state:
            assert game_state == client.connection.game_state_context.ressource
            assert game_state.__class__ == GameState

    def test_wait_until(self):
        client = Client()
        client.connection = ClientConnection(None, None)
        thread = threading.Thread(target=client.wait_until, args=[lambda game_state: hasattr(game_state, "foobar")])
        thread.start()
        assert thread.is_alive()
        client.connection.game_state_context.ressource.foo = "bar"
        assert thread.is_alive()
        client.connection.game_state_context.ressource.foobar = "baz"
        thread.join(timeout=0.1)
        assert not thread.is_alive()
        with freeze_time() as frozen_time:
            exceptions = queue.Queue()

            def test_function():
                try:
                    client.wait_until(lambda game_state: hasattr(game_state, "bizbaz"))
                except Exception as e:
                    exceptions.put(e)
                    exceptions.task_done()

            thread = threading.Thread(target=test_function)
            thread.start()
            assert thread.is_alive()
            frozen_time.tick()
        thread.join()
        assert not exceptions.empty()
        exception = exceptions.get()
        assert exception.__class__ == TimeoutError

    def test_try_to(self):
        client = Client()
        client.connection = ClientConnection(None, None)

        def test_function():
            foobar = client.try_to(lambda game_state: game_state.foo["bar"])
            assert foobar == "baz"

        thread = threading.Thread(target=test_function)
        thread.start()
        client.connection.game_state_context.ressource.foo = {"bar": "baz"}
        thread.join(timeout=0.1)
        assert not thread.is_alive()
        with freeze_time() as frozen_time:
            exceptions = queue.Queue()

            def timeout_test_function():
                try:
                    barfoo = client.try_to(lambda game_state: game_state.bar["foo"])
                    assert barfoo == "biz"
                except Exception as e:
                    exceptions.put(e)
                    exceptions.task_done()

            thread = threading.Thread(target=timeout_test_function)
            thread.start()
            assert thread.is_alive()
            frozen_time.tick()
        thread.join()
        assert not exceptions.empty()
        exception = exceptions.get()
        assert exception.__class__ == TimeoutError

    def test_dispatch_event(self):
        client = Client()

        class MockConnection:
            called_with = []

            def dispatch_event(self, *args, **kwargs):
                self.called_with.append((args, kwargs))

        called_callback = []

        def ack_callback():
            called_callback.append(True)

        client.connection = MockConnection()
        client.dispatch_event("BIZBAZ")
        assert len(MockConnection.called_with) == 1
        client.dispatch_event("BIZBAZ", "foobar", retries=3, ack_callback=ack_callback)
        assert len(MockConnection.called_with) == 2
        foobar_dispatch = MockConnection.called_with[-1]
        assert foobar_dispatch[0][0].handler_args == ["foobar"]
        foobar_dispatch[0][1]()
        assert True in called_callback
        foobar_dispatch[0][2]()
        assert len(MockConnection.called_with) == 3
        foobar_dispatch = MockConnection.called_with[-1]
        foobar_dispatch[0][2]()
        assert len(MockConnection.called_with) == 4
        foobar_dispatch = MockConnection.called_with[-1]
        foobar_dispatch[0][2]()
        assert len(MockConnection.called_with) == 5
        assert MockConnection.called_with[-1][0][2] is None
