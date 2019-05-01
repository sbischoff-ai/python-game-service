"""Example game backend"""

import sys
from pygase import GameState, Backend

initial_game_state = GameState(
    players={},  # dict with `player_id: player_dict` entries
    chaser_id=None,  # id of player who is chaser
    protection=None,  # wether protection from the chaser is active
    countdown=0.0,  # countdown until protection is lifted
)


def on_join(player_name, game_state, dt):
    print(f"Player {player_name} joined.")
    # Count up for player ids, starting with 1.
    player_id = max(game_state.players.keys()) + 1 if game_state.players else 1
    return {
        "players": {player_id: {"name": player_name, "position": (0, 0)}},
        "chaser_id": player_id if game_state.chaser_id is None else game_state.chaser_id,
    }


def on_move(player_id, new_position, game_state, dt):
    return {"players": {player_id: {"position": new_position}}}


def time_step(game_state, dt):
    # Before a player joins, updating the game state is unnecessary.
    if game_state.chaser_id is None:
        return {}
    # If protection mode is on, all players are safe from the chaser.
    if game_state.protection:
        new_countdown = game_state.countdown - dt
        return {"countdown": new_countdown, "protection": True if new_countdown >= 0.0 else False}
    # Check if the chaser got someone.
    chaser = game_state.players[game_state.chaser_id]
    for player_id, player in game_state.players.items():
        if not player_id == game_state.chaser_id:
            # Calculate their distance to the chaser.
            dx = player["position"][0] - chaser["position"][0]
            dy = player["position"][1] - chaser["position"][1]
            distance_squared = dx * dx + dy * dy
            # Whoever the chaser touches becomes chaser and the protection countdown starts.
            if distance_squared < 15:
                print(f"{player['name']} has been caught")
                return {"chaser_id": player_id, "protection": True, "countdown": 5.0}
    return {}


Backend(
    initial_game_state=initial_game_state,
    time_step_function=time_step,
    event_handlers={"JOIN": on_join, "MOVE": on_move},
).run(hostname="localhost", port=8080)
