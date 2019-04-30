# -*- coding: utf-8 -*-
"""Create smooth and scalable online and LAN multiplayer games easily.

PyGaSe, or Python Game Service, is a library (or framework, whichever term you prefer) that provides
a complete set of high-level components for real-time networking for games.

As a user of this library you will only need classes and functions directly imported from `pygase`:

```python
# For clients:
from pygase import Client

# For backends:
from pygase import GameState, GameStateStore, GameStateMachine, Server
# Not necessary but might come in handy:
from pygase import get_availabe_ip_addresses
```

"""

from pygase.client import Client
from pygase.backend import Server, GameStateStore, GameStateMachine
from pygase.gamestate import GameState
from pygase.utils import get_available_ip_addresses
