# Getting Started

This little starter guide demonstrates the basics of setting up und running a backend,
connecting a client and communication via events.

## Backend

To set up a simple PyGaSe backend we will need two classes:
```python
from pygase import GameState, Backend
```

First we define our initial game state:
```python
# Let there be an imaginary enemy at position 0 with 100 health points.
initial_game_state = GameState(position=0.0, hp=100)
```
The `GameState` constructor uses keyword arguments to initialize game state attributes.
(We have to use built-in types such as `int`, `str` or `dict`, so the game state is serializable.)
In this case our game state resembles the dict `{"position": 0.0, "hp": 100}` at the start of the game.

Next we define a time step function for the game loop:
```python
import math

def time_step(game_state, dt):
    # Make the imaginary enemy move in sinuous lines like a drunkard.
    new_position = game_state.position += math.sin(dt)
    return {"position": new_position}
```
The `time_step` function represents one iteration of the game loop and takes the current `game_state` as an argument,
in order to return a `dict` containing all the changes to the game state. By default it will be called 50 times per
second (or once every 0.02 seconds, respectively). However, the actual interval may turn out somewhat longer and differ
from time to time, which is why the time step function also gets the time since the last time step in seconds (`dt`).
In this example our game loop will have the enemies `position` continously oscillating between -1.0 and 1.0.

---
*The backend should always have authority over the game logic and be the single point of truth for the shared state.*
*It might however be beneficial to performance and a smooth feel of a game to pre-compute some game logic client-side*
*and only validate it in the backend.*

---

Now we can initialize and run the backend:
```python
backend = Backend(initial_game_state, time_step)
backend.run('localhost', 8080)
```
Mind that this `run` call is blocking, so whatever we put after there will not be executed
until the backend is shut down again.

Put all together, our first super simple PyGaSe backend looks like this:
```python
# backend.py

import math
from pygase import GameState, Backend

# Let there be an imaginary enemy at position 0 with 100 health points.
initial_game_state = GameState(position=0, hp=100)

def time_step(game_state, dt):
    # Make the imaginary enemy move in sinuous lines like a drunkard.
    new_position = game_state.position += math.sin(dt)
    return {"position": new_position}

backend = Backend(initial_game_state, time_step)
backend.run('localhost', 8080)
```

## Client

If we run `python backend.py` it starts a server that just sits there until we terminate the python process.
To interact with it we could connect a client in an interactive python session in another console window:
```python
>>> from pygase import Client
>>> client = Client()
>>> client.connect_in_thread(port=8080) # hostname="localhost" is default
<Thread(Thread-1, started 24096)> # returns the corresponding thread
>>> with client.access_game_state() as game_state:
...   print(game_state.position)
...   print(game_state.hp)
... 
0.7904802223420048
100
>>> with client.access_game_state() as game_state:
...   print(game_state.position)
... 
-0.29265129683264307
>>> 
```
We have to connect in a thread here, because a blocking `Client.connect()` call would have made it impossible
to interact with the client in the same terminal session. We have to access the game state in a `with` block like
this to ensure that the client is not updating it as we use it. But we also have to be careful not to leave this
`with` block unterminated indefinitely, which would block the client from synchronizing the game state.
However, reading only is a rather one-sided kind of interaction. To have the client talk to the backend we will
use events.

## Events

First we need to register an event handler on the backend side or the event will do nothing:
```python
# A client might choose to attack the drunken master.
def on_attack(attack_position, game_state, **kwargs):
    # Check if the attack landed near enough to hit.
    if abs(attack_position - game_state.position) < 0.1:
        print("Hit!")
        # Subtract the attacks damage from the enemies health.
        return {"hp": game_state.hp - 10}
    print("Missed.")
    return {}

backend = Backend(
    initial_game_state,
    time_step,
    event_handlers={"ATTACK": on_attack}
)
backend.run('localhost', 8080)
```
The event handler function `on_attack` works similar to the time step function, only that it receives additional
keyword arguments like the current `game_state` in this case or the `attack_position`, which we assume to be attached
to the event by the client.

Having extended the backend like this we can now restart it and try out the event in a client terminal session:
```python
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> with client.access_game_state() as game_state:
...   print(game_state.position)
...   print(game_state.hp) # Check if we hit.
... 
-0.1760756199485871
100
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> with client.access_game_state() as game_state:
...   print(game_state.hp) # Check again ...
... 
100
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> with client.access_game_state() as game_state:
...   print(game_state.hp) # ... and again.
... 
90
>>> 
```
This is me trying repeadedly to land a hit on position 0.5. If you look at the console output
of the backend process, you might see something like this:
```
Missed.
Missed.
Hit!
Missed.
```
It's not very practical to have to switch the console windows, it would be better if the client
received some feedback after an attack. Events can also flow from backend to client, which works pretty
much the same way as the other way around.

First we adjust the backends attack event handler to send back a feedback event:
```python
backend = Backend(initial_game_state, time_step)

# A client might choose to attack the drunken master.
def on_attack(attack_position, client_address, game_state, **kwargs):
    # Check if the attack landed near enough to hit.
    if abs(attack_position - game_state.position) < 0.1:
        backend.server.dispatch_event("ATTACK_FEEDBACK", "Hit!", target_client=client_address)
        # Subtract the attacks damage from the enemies health.
        return {"hp": game_state.hp - 10}
    backend.server.dispatch_event("ATTACK_FEEDBACK", "Missed.", target_client=client_address)
    return {}

backend.game_state_machine.register_event_handler("ATTACK", on_attack)
backend.run('localhost', 8080)
```
Here we used another one of the keyword arguments PyGaSe passes to the event handler, the `client_address`
from which the event was sent. Along with the event data, a string containing the feedback message, we also
set the target client for our event. The default for `target_client` is `"all"` which broadcasts the event.

---
*As you can see, the `dispatch_event` method we used is not a member of `backend` but of `backend.server`*
*and `register_event_handler` is a member of `backend.game_state_machine`.*
*In fact, a PyGaSe backend consists of three main components:*
- *A `Server` that deals with connected clients.*
- *A `GameStateStore` which is where the backend keeps track of the state.*
- *A `GameStateMachine` that runs the whole game logic simulation and produces state updates.*

---

Now we only need to register an appropriate event handler on the client side:
```python
>>> client.register_event_handler("ATTACK_FEEDBACK", print)
>>> client.dispatch_event("ATTACK", attack_position=0.5)
Missed.
>>> client.dispatch_event("ATTACK", attack_position=0.5)
Missed.
>>> for i in range(5):
...   client.dispatch_event("ATTACK", attack_position=i*2.0/5-1)
... 
Missed.
Hit!
Missed.
Missed.
Missed.
```
Much better. We get direct feedback and even found an exploit that allows us to land a guaranteed hit
by using a `for` loop. Registering the built-in function `print` as the event handler callback works in this case,
because the handler only receives one argument: the string that the backend attached to the event in
`backend.server.dispatch_event()`.

---
*A proper client for this game, with a UI and everything, would probably not allow to send attack events in such a way.*
*Still, this is how cheats and hacks find their way into an online game, which is why the backend should*
*validate some of the events it gets. In this case for example, it might check if `ATTACK` events are coming in at an*
*unreasonably high frequency.*

---

### Conclusion

Up to now we had to nastily interrupt the backend process and the client thread by hand in order to end a session.
Of course we can also properly terminate everything, for example with
```python
>>> client.disconnect(shutdown_server=True)
```
in the client terminal session. Only the first player to connect will have the permission to shutdown the server
like this. The backend can also shut itself down with `backend.shutdown()`.

---

**To conclude the conclusion:**
We have set up a small PyGaSe backend that simulates a moving enemy and handles attack events.
Right now, the enemy would never die and its `hp` would just go into the negative numbers after you hit zero.
So good next steps might be to implement a way for this game to end by defeating the drunken master or maybe have
the enemy defend itself. Also, a graphical UI wouldn't hurt (I recommend the awesome 
[Arcade library](http://arcade.academy) for this).

To see how this might be done with PyGaSe you can look through the API reference here or you can take a peek into
[this little example game of tag](https://github.com/sbischoff-ai/pygase/tree/master/chase), which uses PyGaSe and
[pygame](https://www.pygame.org/news).

---
For the sake of completeness:
```python
# backend.py

import math
from pygase import GameState, Backend

### SETUP ###

# Let there be an imaginary enemy at position 0 with 100 health points.
initial_game_state = GameState(position=0, hp=100)

# Define what happens in an iteration of the game loop.
def time_step(game_state, dt):
    # Make the imaginary enemy move in sinuous lines like a drunkard.
    new_position = game_state.position += math.sin(dt)
    return {"position": new_position}

# Create the backend.
backend = Backend(initial_game_state, time_step)

### EVENT HANDLERS ###

def on_attack(attack_position, client_address, game_state, **kwargs):
    # Check if the attack landed near enough to hit.
    if abs(attack_position - game_state.position) < 0.1:
        backend.server.dispatch_event("ATTACK_FEEDBACK", "Hit!", target_client=client_address)
        # Subtract the attacks damage from the enemies health.
        return {"hp": game_state.hp - 10}
    backend.server.dispatch_event("ATTACK_FEEDBACK", "Missed.", target_client=client_address)
    return {}

backend.game_state_machine.register_event_handler("ATTACK", on_attack)

### MAIN PROCESS ###

if __name__ == "__main__":
    backend.run('localhost', 8080)
```
