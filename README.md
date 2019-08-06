[![Build Status](https://dev.azure.com/pxlbrain/pygase/_apis/build/status/sbischoff-ai.pygase?branchName=master)](https://dev.azure.com/pxlbrain/pygase/_build/latest?definitionId=2&branchName=master)
![Azure DevOps tests (branch)](https://img.shields.io/azure-devops/tests/pxlbrain/pygase/2/master.svg)
![Azure DevOps coverage (branch)](https://img.shields.io/azure-devops/coverage/pxlbrain/pygase/2/master.svg)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
![PyPI](https://img.shields.io/pypi/v/pygase.svg)
# PyGaSe
**Py**thon **Ga**me **Se**rver

A package for Python 3.6+ that contains a game-ready client-server architecture and UDP-based network protocol.

It deals with problems such as package loss or network congestion so you don't have to. Instead it gives you
a high-level API to easily connect clients and backends that share a synchronized game state and exchange events.
The async framework for this one is [curio](https://github.com/dabeaz/curio), which I highly recommend.

PyGaSe is built to be easy to use, lightweight, fast, scalable and reliable.
You can build a fast-paced real-time online game with this.
You can also build a large-scale MMO with thousands of clients if you like.

I'm actively developing PyGaSe in the context of several Indie game projects and I'm happy to share it.

---
***BREAKING CHANGE**: Version 0.2.0 is basically a new API and updating from 0.1.9 or lower will break you code.*
*It is also much more stable, flexible and powerful, so make sure to use 0.2.0 or higher.*

---

### Installation
```
pip install pygase
```
or better yet `poetry add pygase`. Seriously, use [poetry](https://github.com/sdispater/poetry), it's a revelation.

## Usage

### API Reference & Tutorials

For API documentation and a *Getting Started* section go [here](https://sbischoff-ai.github.io/pygase/).

### Example

[This example game](https://github.com/sbischoff-ai/pygase/tree/master/chase) implements an online game of tag,
in which players can move around, while one of them is the chaser who has to catch another player.
A player who has been catched becomes the next chaser and can catch other players after a 5s protection countdown.

Run `server.py` first, then run `client.py` in additional terminal sessions to add players.
Only use the same player name once.

### Debugging & Logging

You can use the standard `logging` module. On level `INFO` you will get logging output for events such as
startups, shutdowns, new connections or disconnects. On `DEBUG` level you get detailed output right down to the level
of sending, receiving and handling single network packages.

Debug logs are also a good way to understand the inner workings of PyGaSe.

---
## Changes

### 0.3.1
- improved documentation
- minor logging fixes

### 0.3.0
- sticking to SemVer from here on out
- logging added using the standard `logging` module
- improve event handler arguments
- `Backend` class added to reduce server-side boilerplate
- various bugfixes

### 0.2.0
- complete overhaul of pygase 0.1.x with breaking API changes
