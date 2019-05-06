import pytest
from pygase.utils import Sqn, Sendable, get_available_ip_addresses


class TestSendable:
    def test_bytepacking(self):
        class SomeClass(Sendable):
            def __init__(self, a, b):
                self.a = a
                self.b = b

            def foo(self):
                return "bar"

        obj = SomeClass(1, 2)
        obj.hello = {",": ["World", "!"]}
        bytepack = obj.to_bytes()
        unpacked_obj = SomeClass.from_bytes(bytepack)
        assert unpacked_obj == obj
        assert unpacked_obj.foo() == "bar"
        with pytest.raises(TypeError) as exception:
            SomeClass.from_bytes("This is not a Sendable".encode("utf-8"))
        assert str(exception.value) == "Bytes could no be parsed into SomeClass."

        class SomeOtherClass(Sendable):
            pass

        assert SomeOtherClass() == SomeOtherClass.from_bytes(SomeOtherClass().to_bytes())


class TestSqn:
    def test_initialize_valid_values(self):
        for i in range(Sqn._max_sequence + 1):
            s = Sqn(i)
            assert s == i

    def test_initialize_negative_values(self):
        for i in range(-1, -(Sqn._max_sequence + 2), -1):
            with pytest.raises(ValueError) as error:
                Sqn(i)
            assert str(error.value) == "sequence numbers must not be negative"

    def test_initialize_with_overflowing_value(self):
        for i in range(Sqn._max_sequence + 1, 2 * Sqn._max_sequence):
            with pytest.raises(ValueError) as error:
                Sqn(i)
            assert str(error.value) == "value exceeds maximum sequence number"

    def test_add_within_sequence(self):
        s = Sqn(0)
        for i in range(1, Sqn._max_sequence + 1):
            s += Sqn(1)
            assert s == i
            assert s.__class__ == Sqn

    def test_add_within_sequence_with_ints(self):
        s = Sqn(0)
        for i in range(1, Sqn._max_sequence + 1):
            s += 1
            assert s == i
            assert s.__class__ == Sqn

    def test_sequence_wrap_around(self):
        s = Sqn(Sqn._max_sequence)
        s += Sqn(1)
        assert s == 1

    def test_sequence_wrap_around_with_int(self):
        s = Sqn(Sqn._max_sequence)
        s += 1
        assert s == 1

    def test_add_negative_int(self):
        s = Sqn(2)
        s += -1
        assert s == 1 and s.__class__ == Sqn

    def test_add_negative_int_with_larger_norm(self):
        s = Sqn(2)
        with pytest.raises(ValueError) as error:
            s += -3
        assert str(error.value) == "sequence numbers must not be negative"

    def test_small_difference_within_sequence(self):
        s1 = Sqn(2)
        s2 = Sqn(5)
        assert s2 - s1 == 3
        assert s1 - s2 == -3
        assert s2 > s1 and s1 < s2

    def test_small_difference_around_sequence_edge(self):
        s1 = Sqn(2)
        s2 = Sqn(Sqn._max_sequence - 2)
        assert s2 - s1 == -4
        assert s1 - s2 == 4
        assert s1 > s2 and s2 < s1

    def test_symmetry(self):
        s = Sqn(1)
        greater = 0
        lower = 0
        for i in range(1, Sqn._max_sequence + 1):
            if Sqn(i) > s:
                greater += 1
            elif Sqn(i) < s:
                lower += 1
        assert greater > 0 and greater == lower

    def test_large_distance(self):
        assert Sqn(50000) - Sqn(20000) == 30000
        assert Sqn(Sqn._max_sequence - 100) - Sqn(20000) == -20100

    def test_bytes(self):
        for i in range(2 * Sqn._bytesize):
            b = Sqn(i).to_sqn_bytes()
            assert len(b) == Sqn._bytesize
            assert b.__class__ == bytes
            assert Sqn.from_sqn_bytes(b) == Sqn(i)

    def test_subclassing_and_bytesize_change(self):
        class subSqn(Sqn):
            pass

        subSqn.set_bytesize(4)
        assert subSqn._bytesize == 2 * Sqn._bytesize
        assert (subSqn._max_sequence + 1) / (Sqn._max_sequence + 1) == Sqn._max_sequence + 1
        assert len(subSqn(12532).to_sqn_bytes()) == 4


class TestUtilFunctions:
    def test_get_IpAddresses(self):
        ips = get_available_ip_addresses()
        assert "127.0.0.1" in ips
