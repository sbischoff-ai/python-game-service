"""Example game client"""

import pygame
import pygame.locals
from pygase import Client


client = Client()

# Connect the client and join a new player to the server.
client.connect_in_thread(hostname="localhost", port=8080)
local_player_name = input("Player name: ")
client.dispatch_event("JOIN", local_player_name)

# Get the players ID from the server.
def get_player_id(game_state):
    for player_id, player in game_state.players.items():
        if player["name"] == local_player_name:
            return player_id


local_player_id = client.try_to(get_player_id)

# Set up some helpful stuff for pygame.
keys_pressed = set()
clock = pygame.time.Clock()


def draw_player(screen, position, is_chaser, is_self):
    """Draw players as colored circles.

        - Green: Yourself
        - Blue: Others
        - Red: The chaser

    """
    if is_self:
        color = (50, 255, 50)
    else:
        color = (255, 50, 50) if is_chaser else (50, 50, 255)
    pygame.draw.circle(screen, color, position, 10)


# Initialize a pygame screen.
pygame.init()
screen_width = 640
screen_height = 420
screen = pygame.display.set_mode((screen_width, screen_height))

# the actual game loop
game_is_running = True
while game_is_running:
    dt = clock.tick(40)
    # Clear the screen.
    screen.fill((0, 0, 0))
    # Handle pygame input events.
    for event in pygame.event.get():
        if event.type == pygame.locals.QUIT:
            game_is_running = False
        if event.type == pygame.locals.KEYDOWN:
            keys_pressed.add(event.key)
        if event.type == pygame.locals.KEYUP:
            keys_pressed.remove(event.key)
    # Handle player movement.
    dx, dy = 0, 0
    if pygame.locals.K_DOWN in keys_pressed:
        dy += int(0.1 * dt)
    elif pygame.locals.K_UP in keys_pressed:
        dy -= int(0.1 * dt)
    elif pygame.locals.K_RIGHT in keys_pressed:
        dx += int(0.1 * dt)
    elif pygame.locals.K_LEFT in keys_pressed:
        dx -= int(0.1 * dt)
    # Safely access the synchronized shared game state.
    with client.access_game_state() as game_state:
        # Notify server about player movement.
        old_position = game_state.players[local_player_id]["position"]
        client.dispatch_event(
            event_type="MOVE",
            player_id=local_player_id,
            new_position=((old_position[0] + dx) % screen_width, (old_position[1] + dy) % screen_height),
        )
        # Draw all players.
        for player_id, player in game_state.players.items():
            is_chaser = player_id == game_state.chaser_id
            is_self = player_id == local_player_id
            draw_player(screen, player["position"], is_chaser, is_self)
    # Do the thing.
    pygame.display.flip()

# Clean up.
pygame.quit()
client.disconnect(shutdown_server=True)
