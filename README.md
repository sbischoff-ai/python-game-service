[![Build Status](https://dev.azure.com/pxlbrain/pygase/_apis/build/status/sbischoff-ai.pygase?branchName=master)](https://dev.azure.com/pxlbrain/pygase/_build/latest?definitionId=2&branchName=master)
![Azure DevOps tests (branch)](https://img.shields.io/azure-devops/tests/pxlbrain/pygase/2/master.svg)
![Azure DevOps coverage (branch)](https://img.shields.io/azure-devops/coverage/pxlbrain/pygase/2/master.svg)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
![PyPI](https://img.shields.io/pypi/v/pygase.svg)
# PyGaSe
**Py**thon**Ga**me**Se**rver

A Python package that contains a versatile lightweight UDP-based client-server API and network protocol for 
real-time online games.

---
***BREAKING CHANGE**: Version 0.2.0 is basically a new API and updating from 0.1.9 or lower will break you code.*
*It is also much more stable, flexible and powerful, so make sure to use it instead.*

---

### Installation
```
pip install pygase
```

## Usage

Tutorials and How-Tos will come in the future. For now there is a little example game and API docs.

### Example

[This example game](https://github.com/sbischoff-ai/pygase/tree/master/chase) implements an online game of chase,
in which players can move around, while one of them is the chaser who has to catch another player.
A player who has been catched becomes the next chaser and can catch other players after a 5s protection countdown.

### API Reference

For a complete API documentation look in [here](https://sbischoff-ai.github.io/pygase/).

---

**TODOS:**
 - proper exception handling
 - logging
 - debugging and monitoring tools
 - 95% test coverage
 - tutorials, how-tos and documentation website
