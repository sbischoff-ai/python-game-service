# -*- coding: utf-8 -*-

import threading

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

            def test_function():
                with pytest.raises(TimeoutError):
                    client.wait_until(lambda game_state: hasattr(game_state, "bizbaz"))

            thread = threading.Thread(target=test_function)
            thread.start()
            assert thread.is_alive()
            frozen_time.tick()
        thread.join()
        assert not thread.is_alive()

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

            def timeout_test_function():
                with pytest.raises(TimeoutError):
                    barfoo = client.try_to(lambda game_state: game_state.bar["foo"])
                    assert barfoo == "biz"

            thread = threading.Thread(target=timeout_test_function)
            thread.start()
            assert thread.is_alive()
            frozen_time.tick()
        thread.join()
        assert not thread.is_alive()
