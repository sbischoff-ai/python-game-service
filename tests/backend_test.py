# -*- coding: utf-8 -*-

import curio
from freezegun import freeze_time
import pytest

from helpers import assert_timeout

from pygase.backend import Server, GameStateStore, GameStateMachine, Backend
from pygase.gamestate import GameState, GameStateUpdate, GameStatus
from pygase.connection import ClientPackage
from pygase.event import UniversalEventHandler


class TestServer:
    def test_instantiation(self):
        server = Server(GameStateStore())
        assert isinstance(server.game_state_store, GameStateStore)
        assert isinstance(server._universal_event_handler, UniversalEventHandler)

    def test_run_async(self):
        server = Server(GameStateStore())

        async def test_task():
            await curio.spawn(server.run, 1234)
            await assert_timeout(1, lambda: server.hostname == "localhost")
            assert server._port == 1234
            await server.shutdown()
            return True

        assert curio.run(test_task)

    def test_dispatch_event(self):
        server = Server(GameStateStore())

        class MockConnection:
            called_with = []

            def dispatch_event(self, *args, **kwargs):
                self.called_with.append((args, kwargs))

        foo_connection = MockConnection()
        server.connections[("foo", 1)] = foo_connection
        server.connections[("bar", 1)] = MockConnection()
        server.dispatch_event("BIZBAZ")
        assert len(MockConnection.called_with) == 2
        server.dispatch_event("BIZBAZ", "foobar", target_client=("foo", 1), retries=3, ack_callback=id)
        assert len(MockConnection.called_with) == 3
        foobar_dispatch = MockConnection.called_with[-1]
        assert foobar_dispatch[0][0].handler_args == ["foobar"]
        assert foobar_dispatch[0][1]() == id(foo_connection)
        foobar_dispatch[0][2]()
        assert len(MockConnection.called_with) == 4
        foobar_dispatch = MockConnection.called_with[-1]
        foobar_dispatch[0][2]()
        assert len(MockConnection.called_with) == 5
        foobar_dispatch = MockConnection.called_with[-1]
        foobar_dispatch[0][2]()
        assert len(MockConnection.called_with) == 6
        assert MockConnection.called_with[-1][0][2] is None


class TestGameStateStore:
    def test_instantiation(self):
        store = GameStateStore()
        assert store._game_state == GameState()
        assert store._game_state_update_cache == [GameStateUpdate(0)]

    def test_push_update(self):
        store = GameStateStore()
        store.push_update(GameStateUpdate(1, test="foobar"))
        assert len(store._game_state_update_cache) == 2
        assert store.get_game_state().time_order == 1
        assert store.get_game_state().test == "foobar"

    def test_safe_concurrent_cache_access(self):
        store = GameStateStore()
        store.push_update(GameStateUpdate(2))
        counter = 0
        for update in store.get_update_cache():
            counter += 1
            if update.time_order == 2:
                store.push_update(GameStateUpdate(3))
        assert counter == 2
        counter = 0
        for update in store.get_update_cache():
            counter += 1
            if update.time_order == 0:
                del store._game_state_update_cache[2]
        assert counter == 3
        assert len(store.get_update_cache()) == 2

    def test_cache_size(self):
        store = GameStateStore()
        for i in range(2 * store._update_cache_size):
            assert len(store.get_update_cache()) == min(i + 1, store._update_cache_size)
            store.push_update(GameStateUpdate(i + 1))
            assert sum(store.get_update_cache()).time_order == i + 1


class TestGameStateMachine:
    def test_instantiation(self):
        state_machine = GameStateMachine(GameStateStore())
        assert state_machine.game_time == 0
        assert state_machine._game_state_store._game_state_update_cache == [GameStateUpdate(0)]

    def test_abstractness(self):
        state_machine = GameStateMachine(GameStateStore())
        with pytest.raises(NotImplementedError):
            state_machine.time_step(GameState(), 0.1)

    def test_game_loop(self):
        class MyStateMachine(GameStateMachine):
            def time_step(self, game_state, dt):
                test = game_state.test + 1
                return {"test": test}

        store = GameStateStore(GameState(0, test=0))
        state_machine = MyStateMachine(store)

        async def test_task():
            with freeze_time() as frozen_time:
                game_loop = await curio.spawn(state_machine.run_game_loop, 1)
                for _ in range(10):
                    frozen_time.tick()
                    await curio.sleep(0)
                await state_machine.stop()
                await game_loop.join()
            return True

        assert curio.run(test_task)
        assert store.get_game_state().time_order == 12
        assert store.get_game_state().test == 10
        assert state_machine.game_time == 10
        assert store.get_game_state().game_status == GameStatus.get("Paused")


class TestBackend:
    def test_instantiation(self):
        time_step = lambda game_state, dt: {}
        backend = Backend(initial_game_state=GameState(), time_step_function=time_step)
        assert isinstance(backend.game_state_store, GameStateStore)
        assert backend.game_state_store._game_state == GameState()
        assert isinstance(backend.game_state_machine, GameStateMachine)
        assert backend.game_state_machine.time_step == time_step
        assert isinstance(backend.server, Server)
        assert backend.server.game_state_store == backend.game_state_store
