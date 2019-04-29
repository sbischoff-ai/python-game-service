# -*- coding: utf-8 -*-

import curio
from freezegun import freeze_time
import pytest

from helpers import assert_timeout

from pygase.backend import Server, GameStateStore, GameStateMachine
from pygase.gamestate import GameState, GameStateUpdate, GameStatus
from pygase.connection import ClientPackage
from pygase.event import UniversalEventHandler


class TestServer:
    def test_instantiation(self):
        server = Server(GameStateStore())
        assert server.game_state_store.__class__ == GameStateStore
        assert server._universal_event_handler.__class__ == UniversalEventHandler

    def test_run_async(self):
        server = Server(GameStateStore())

        async def test_task():
            await curio.spawn(server.run, 1234)
            await assert_timeout(1, lambda: server.hostname == "localhost")
            assert server._port == 1234
            await server.shutdown()
            return True

        assert curio.run(test_task)


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
