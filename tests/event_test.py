# -*- coding: utf-8 -*-

from pygase.event import Event, UniversalEventHandler


class TestEvent:
    def test_bytepacking(self):
        event1 = Event("TEST", 1, 2, 3)
        event2 = Event.from_bytes(event1.to_bytes())
        assert event1 == event2
