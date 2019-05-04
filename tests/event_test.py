# -*- coding: utf-8 -*-

import pytest
import curio

from pygase.event import Event, UniversalEventHandler


class TestEvent:
    def test_bytepacking(self):
        event1 = Event("TEST", 1, 2, 3)
        event2 = Event.from_bytes(event1.to_bytes())
        assert event1 == event2

    def test_synchronous_event_handler(self):
        handler = UniversalEventHandler()
        testlist = []

        def on_foo(bar):
            testlist.append(bar)

        assert not handler.has_event_type("FOO")
        handler.register_event_handler("FOO", on_foo)
        assert handler.has_event_type("FOO")
        curio.run(handler.handle, Event("FOO", "baz"))
        assert "baz" in testlist
        handler.register_event_handler("BAR", lambda: testlist.pop())
        assert curio.run(handler.handle, Event("BAR")) == "baz"
        assert not testlist

    def test_asynchronous_event_handler_with_kwarg(self):
        handler = UniversalEventHandler()
        testlist = []

        async def on_foo(biz=0, bar="nobizbaz"):
            testlist.append(bar)

        handler.register_event_handler("FOO", on_foo)
        curio.run(handler.handle, Event("FOO", bar="bizbaz"))
        assert "bizbaz" in testlist

    def test_register_nonsense(self):
        handler = UniversalEventHandler()
        with pytest.raises(TypeError, match="'list' object is not callable"):
            handler.register_event_handler("FOO", ["Not a function"])
