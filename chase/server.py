"""Example game backend"""

import random
from pygase import GameState, Backend


### SETUP ###

# Initialize the game state.
initial_game_state = GameState(
    players={},  # dict with `player_id: player_dict` entries
    chaser_id=None,  # id of player who is chaser
    protection=None,  # wether protection from the chaser is active
    countdown=0.0,  # countdown until protection is lifted
)

# Define the game loop iteration function.
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
            # Whoever the chaser touches becomes the new chaser and the protection countdown starts.
            if distance_squared < 15:
                print(f"{player['name']} has been caught")
                return {"chaser_id": player_id, "protection": True, "countdown": 5.0}
    return {}


# "MOVE" event handler
def on_move(player_id, new_position, **kwargs):
    return {"players": {player_id: {"position": new_position}}}


# Create the backend.
backend = Backend(initial_game_state, time_step, event_handlers={"MOVE": on_move})

# "JOIN" event handler
def on_join(player_name, game_state, client_address, **kwargs):
    print(f"{player_name} joined.")
    player_id = len(game_state.players)
    # Notify client that the player successfully joined the game.
    backend.server.dispatch_event("PLAYER_CREATED", player_id, target_client=client_address)
    return {
        # Add a new entry to the players dict
        "players": {player_id: {"name": player_name, "position": (random.random() * 640, random.random() * 420)}},
        # If this is the first player to join, make it the chaser.
        "chaser_id": player_id if game_state.chaser_id is None else game_state.chaser_id,
    }


# Register the "JOIN" handler.
backend.game_state_machine.register_event_handler("JOIN", on_join)

### MAIN PROCESS ###

if __name__ == "__main__":
    backend.run(hostname="localhost", port=8080)
