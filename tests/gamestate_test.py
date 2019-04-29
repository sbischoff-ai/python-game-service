# -*- coding: utf-8 -*-

from pygase.gamestate import GameState, GameStateUpdate, GameStatus, TO_DELETE


class TestGameState:
    def test_bytepacking(self):
        game_state = GameState()
        bytepack = game_state.to_bytes()
        unpacked_game_state = GameState.from_bytes(bytepack)
        assert game_state == unpacked_game_state

    def test_game_state_instantiation(self):
        game_state = GameState()
        assert game_state.time_order == 0
        assert game_state.game_status == GameStatus.get("Paused")
        paused_game_state = GameState(game_status=GameStatus.get("Active"))
        assert game_state.game_status != paused_game_state.game_status
        paused_game_state.game_status = GameStatus.get("Paused")
        assert game_state == paused_game_state


class TestGameStateUpdate:
    def test_bytepacking(self):
        update = GameStateUpdate(5)
        bytepack = update.to_bytes()
        unpacked_update = GameStateUpdate.from_bytes(bytepack)
        assert update == unpacked_update

    def test_update_arithmetic(self):
        game_state = GameState(time_order=0, game_status=GameStatus.get("Paused"))
        update = GameStateUpdate(time_order=0, test=0)
        game_state += update
        assert not hasattr(game_state, "test") and game_state.time_order == 0
        update.time_order = 1
        game_state += update
        assert game_state.test == 0 and game_state.time_order == 1
        update.time_order = 2
        update.test = TO_DELETE
        game_state += update
        assert not hasattr(game_state, "test") and game_state.time_order == 2
        update.time_order = 1
        update.test = 2
        game_state += update
        assert not hasattr(game_state, "test") and game_state.time_order == 2
        game_state.test = 0
        update += GameStateUpdate(time_order=3, test=TO_DELETE)
        assert update.time_order == 3 and update.test == TO_DELETE
        assert hasattr(game_state, "test") and game_state.time_order == 2
        game_state += update
        assert not hasattr(game_state, "test") and game_state.time_order == 3
        update += GameStateUpdate(time_order=4, test="test")
        assert update.test == "test" and update > game_state
        game_state += (
            GameStateUpdate(time_order=3, test={1: TO_DELETE})
            + GameStateUpdate(time_order=5, test={1: "test1", 2: "test2"})
            + update
        )
        assert game_state.time_order == 5 and game_state.test[1] == "test1"
