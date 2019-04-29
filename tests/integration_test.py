# -*- coding: utf-8 -*-

import curio
from freezegun import freeze_time

from helpers import assert_timeout

from pygase.backend import Server, GameStateMachine, GameStateStore
from pygase.client import Client
from pygase.gamestate import GameState, GameStatus


class TestIntegration:
    def test_client_server_connection(self):
        server = Server(GameStateStore())
        client = Client()

        async def test_task():
            await curio.spawn(server.run)
            await assert_timeout(1, lambda: server.port is not None)
            await curio.spawn(client.connect, server.port)
            await assert_timeout(1, lambda: server.connections != {})
            assert client.connection.remote_address == (server.hostname, server.port)
            await curio.sleep(0)
            await server.shutdown()
            return True

        assert curio.run(test_task)

    def test_connect_disconnect(self):
        init_gamestate = GameState(counter=0, test="foobar")
        state_store = GameStateStore(init_gamestate)
        state_machine = GameStateMachine(state_store)

        def test_update(game_state, dt):
            counter = game_state.counter + 1
            test = "foobar" if counter % 2 == 0 else "barfoo"
            return {"test": test, "counter": counter}

        state_machine.time_step = test_update
        server = Server(state_store)
        client = Client()

        async def test_task(client_shutdown):
            server_task = await curio.spawn(server.run)
            await assert_timeout(1, lambda: server._port is not None)
            client_task = await curio.spawn(client.connect, server.port, server.hostname)
            await assert_timeout(1, lambda: client.connection is not None)
            state_machine_task = await curio.spawn(state_machine.run_game_loop)
            await assert_timeout(1, lambda: state_store.get_game_state().game_status == GameStatus.get("Active"))
            await state_machine.stop()
            await state_machine_task.join()
            await client.disconnect(shutdown_server=client_shutdown)
            await client_task.join()
            if not client_shutdown:
                await server.shutdown()
            await server_task.join()
            return True

        assert curio.run(test_task, True, with_monitor=True)
        assert curio.run(test_task, False, with_monitor=True)


# TODOS: server timeout when connections are gone, backend factory, WIRE UP GAMESTATEMACHINE TO EVENTS
# Improve state_store (accessing state attributes is too lengthy)
