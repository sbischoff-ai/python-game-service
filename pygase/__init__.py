# -*- coding: utf-8 -*-
"""
PyGaSe, or Python Game Service, is a library (or framework, whichever name you prefer) that provides
a complete set of high-level components for real-time networking for games.
"""

from pygase.client import Client
from pygase.backend import Server, GameStateStore, GameStateMachine
from pygase.gamestate import GameState
from pygase.utils import get_available_ip_addresses
