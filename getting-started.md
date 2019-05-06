# Getting Started

This little starter guide demonstrates the basics of setting up und running a backend,
connecting a client and communicating via events.

## Backend

To set up a simple PyGaSe backend you will need two classes:
```python
from pygase import GameState, Backend
```

First you define your initial game state:
```python
initial_game_state = GameState(position=0, hp=100)
```
The `GameState` constructor takes arbitrary keyword arguments to initialize game state attributes.
(Use only built-in types such as `int`, `str` or `dict`.) In this case my game state only consists of the attributes
`position` initialized with a value of `0` and `hp` with 100.

*TL;DR: Put stuff like empty lists of enemies and players or other game world objects here.*

Next you define a time step function for your game loop:
```python
import math

def time_step(game_state, dt):
    new_position = game_state.position += math.sin(dt)
    return {"position": new_position}
```
The `time_step` function represents one iteration of the game loop and takes the current `game_state` as an argument,
in order to return a `dict` containing all the changes to the game state. By default it will be called 50 times per
seconds or once every 0.02 seconds respectively. However, the actual interval may turn out somewhat longer and differ
from time to time, which is why the time step function also gets the time since the last time step in seconds (`dt`).
In this example my game loop will have the `position` continously oscillating between -1 and 1.

*TL;DR: Use this to simulate your game world, like the movement of enemies and bullets or something.*

Now you can initialize and run your backend:
```python
backend = Backend(initial_game_state, time_step)
backend.run('localhost', 8080)
```
That `run` call is blocking, so whatever you put after there will not be executed until the backend is shut down again.

Now this first super simple PyGaSe backend looks like this:
```python
# backend.py

import math
from pygase import GameState, Backend

initial_game_state = GameState(position=0, hp=100)

def time_step(game_state, dt):
    new_position = game_state.position += math.sin(dt)
    return {"position": new_position}

backend = Backend(initial_game_state, time_step)
backend.run('localhost', 8080)
```

## Client

If you run `python backend.py` it starts a server that just sits there until you terminate the python process.
To interact with it we can just connect a client in an interactive python session in another console window:

```python
>>> from pygase import Client
>>> client = Client()
>>> client.connect_in_thread(8080)
<Thread(Thread-1, started 24096)>
>>> with client.acces_game_state() as game_state:
...   print(game_state.position)
...   print(game_state.hp)
... 
0.7904802223420048
100
>>> with client.acces_game_state() as game_state:
...   print(game_state.position)
... 
-0.29265129683264307
>>> 
```

This is a rather one-sided kind of interaction of course. To have the client talk to the backend you
use events.

## Events

First you need to register an event handler on the backend side or the event will do nothing:
```python
def on_attack(attack_position, client_address, game_state, dt):
    if abs(attack_position - game_state.position) < 0.1:
        print("Hit!")
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
The event handler function `on_attack` works similar to the time step function, only that it also has the argument
`client_address` which identifies the sender of the event and can have further additional arguments,
like `attack_position` in this case, which represent data that comes with an event.

Having extended the backend like this we can now run it again and try out the event in a client terminal session again:
```python
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> with client.acces_game_state() as game_state:
...   print(game_state.position)
...   print(game_state.hp)
... 
-0.1760756199485871
100
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> with client.acces_game_state() as game_state:
...   print(game_state.hp)
... 
100
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> client.dispatch_event("ATTACK", attack_position=0.5)
>>> with client.acces_game_state() as game_state:
...   print(game_state.hp)
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
def on_attack(attack_position, client_address, game_state, dt):
    if abs(attack_position - game_state.position) < 0.1:
        backend.server.dispatch_event("ATTACK_FEEDBACK", "Hit!", target_client=client_address)
        return {"hp": game_state.hp - 10}
    backend.server.dispatch_event("ATTACK_FEEDBACK", "Missed.", target_client=client_address)
    return {}
```

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
Much better. We even found an exploit that allows us to land a guaranteed hit using a for loop.
Passing the built-in function `print` as the event handler callback works in this case, because
the handler only gets one argument, the string that the backend attached to the event in
`backend.dispatch_event("ATTACK_FEEDBACK", "Hit!")` and `backend.dispatch_event("ATTACK_FEEDBACK", "Missed.")`.

### Conclusion

A proper client for this game, with a UI and such, would probably not allow to send attack events in such a way.
Still, this is how cheats and hacks find their way into an online game, which is why your backend should always
validate the events it gets. In this case for example it should check if `ATTACK` events are coming in in an
unreasonably high frequency.

Next you could try out to connect with a seconds client from another parallel terminal window and add some
additional functionality. You can also take a peek into
[this example game of chase](https://github.com/sbischoff-ai/pygase/tree/master/chase).
