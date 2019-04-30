# -*- coding: utf-8 -*-
"""Use helpful classes and functions.

Provides utilities used in PyGaSe code or helpful to users of this library.

### Contents
 - *Comparable*: mixin that makes object compare as equal if their type and attributes match
 - *Sendable*: mixin that allows to serialize objects to small bytestrings
 - *NamedEnum*: base class for lists of strings to be mapped to integer values
 - *Sqn*: subclass of `int` for sequence numbers that always fit in 2 bytes
 - *LockedRessource*: class that attaches a `threading.Lock` to a ressource
 - *get_available_ip_addresses*: function that returns a list of local network interfaces

"""

from threading import Lock

import umsgpack
import ifaddr


class Comparable:

    """Compare objects by equality of attributes."""

    def __eq__(self, other) -> bool:
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)


class Sendable(Comparable):

    """Send objects via UDP packages.

    This mixin for classes that are supposed to be sendable as part of a PyGaSe package makes
    objects serializable with the msgpack protocol.
    Sendables can only have attributes of type `str`, `bytes`, `Sqn`, `int`, `float`, `bool`
    as well as `list`s or `tuple`s of such.

    """

    def to_bytes(self) -> bytes:
        """Serialize the object to a compact bytestring."""
        return umsgpack.packb(self.__dict__, force_float_precision="single")

    @classmethod
    def from_bytes(cls, bytepack: bytes):
        """Deserialize a bytestring into an instance of this class.

        #### Arguments
        - `bytepack`: the bytestring to be parsed to a subclass of `Sendable`

        #### Returns
        a copy of an object that was serialized via `Sendable.to_bytes`

        """
        try:
            received_sendable = object.__new__(cls)
            received_sendable.__dict__ = umsgpack.unpackb(bytepack)  # pylint: disable=attribute-defined-outside-init
            return received_sendable
        except (umsgpack.InsufficientDataException, KeyError, TypeError):
            raise TypeError("Bytes could no be parsed into " + cls.__name__ + ".")


class NamedEnum:

    """Map string labels to integer values.

    This is a base class meant to be subclassed to produce a dynamic enum mapping type.

    Example:
    ```python
    class MyEnum(NamedEnum):

        '''Encode labels in integers.
         - "foo"
         - "bar"

        '''


        MyEnum.register("foo")
        MyEnum.register("bar")

        assert MyEnum.get("foo") == 1
        assert MyEnum.get("bar") == 2
        assert MyEnum.get(1) == "foo"
        assert MyEnum.get(2) == "bar"
    ```

    """

    _values: list = []

    # should add advanced type checking for name_or_value
    @classmethod
    def get(cls, name_or_value):
        """Get the value for a label or vice versa.

        #### Arguments
        - `name_or_value`: label or value to de- or encode

        #### Returns
        int value for given string label or vice versa

        #### Raises
         - `TypeError` if argument is neither `int` nor `str`

        """
        if isinstance(name_or_value, int):
            return cls._values[name_or_value]
        if isinstance(name_or_value, str):
            return cls._values.index(name_or_value)
        raise TypeError

    @classmethod
    def register(cls, name: str) -> None:
        """Add a new label to the mapping.

        #### Arguments
        - `name`: string label to register as new enum value

        """
        if name not in cls._values:
            cls._values.append(name)


class Sqn(int):

    """Use finite periodic integers that fit in 2 bytes.

    Subclass of `int` that provides a residue-class-like behaviour of wrapping back to 1 after a maximum value.
    Use it to represent sequence numbers with a fixed number of bytes when you only need well-defined ordering
    within a specific finite scale. 0 represents the state before the sequence has started.

    For the default bytesize of 2 the maximum sequence number is 65535.

    """

    _bytesize: int = 2
    _max_sequence: int = int("1" * (_bytesize * 8), 2)

    @classmethod
    def set_bytesize(cls, bytesize: int) -> None:
        """Redefine the bytesize and wrap-over behaviour for all `Sqn` instances.

        #### Arguments
        - `bytesize`: new size for the `bytes` representation of `Sqn` instances

        """
        cls._bytesize = bytesize
        cls._max_sequence = int("1" * (bytesize * 8), 2)

    @classmethod
    def get_max_sequence(cls) -> int:
        """Return the maximum sequence number after which `Sqn`s wrap back to 1."""
        return cls(cls._max_sequence)

    def __new__(cls, value) -> "Sqn":
        """Create a `Sqn` instance."""
        if value is None:
            value = 0
        elif value > cls._max_sequence:
            raise ValueError("value exceeds maximum sequence number")
        elif value < 0:
            raise ValueError("sequence numbers must not be negative")
        return super(Sqn, cls).__new__(cls, value)  # type: ignore

    def __add__(self, other) -> "Sqn":
        """Add sequence numbers.

        Example:
        ```python
        assert Sqn(2) + Sqn(3) == 5
        assert Sqn(2) + 3 == 5
        assert Sqn.get_max_sequence() == 65535
        assert Sqn(2) + 65535 == 2
        ```

        """
        result = super().__add__(other)
        if result > self._max_sequence:
            result -= self._max_sequence
        return self.__class__(result)

    def __sub__(self, other) -> int:
        """Calculate the difference between sequence numbers.

        Example:
        ```python
        assert Sqn(5) - Sqn(3) == 2
        assert Sqn.get_max_sequence() == 65535
        assert Sqn(5) - Sqn(65530) == 10
        ```

        """
        result = super().__sub__(other)
        threshold = (self._max_sequence - 1) / 2
        if result > threshold:
            result -= self._max_sequence
        elif result < -threshold:
            result += self._max_sequence
        return int(result)

    def __lt__(self, other) -> bool:
        """Check if sequence number is lower than `other`.

        Example:
        ```python
        assert not Sqn(5) < Sqn(3)
        assert Sqn.get_max_sequence() == 65535
        assert not Sqn(5) < Sqn(65500)
        assert Sqn(5) < Sqn(100)
        ```

        """
        return super().__lt__(super().__add__((other - self)))

    def __gt__(self, other) -> bool:
        """Check if sequence number is greater than `other`.

        Example:
        ```python
        assert Sqn(5) > Sqn(3)
        assert Sqn.get_max_sequence() == 65535
        assert Sqn(5) > Sqn(65500)
        assert not Sqn(5) > Sqn(100)
        ```

        """
        return super().__gt__(super().__add__((other - self)))

    def to_sqn_bytes(self) -> bytes:
        """Return representation of the number in exactly the currenly set bytesize.

        The default bytesize is 2.

        """
        return super().to_bytes(self._bytesize, "big")

    @classmethod
    def from_sqn_bytes(cls, bytestring: bytes) -> "Sqn":
        """Return `Sqn` object that was encoded in given bytestring."""
        return cls(super().from_bytes(bytestring, "big"))


class LockedRessource:
    """Access a ressource thread-safely.

    This class makes an object available via a context manager that essentialy attaches a
    `threading.Lock` to it, that threads writing to this object should abide.

    Usage example:
    ```python
    myRessource = { 'foo': 'bar' }
    myLockedRessource = LockedRessource(myRessource)
    with myLockedRessource() as ressource:
        # do stuff without any other threads meddling with the ressource
    ```

    #### Arguments
    - `ressource`: object to be wrapped

    ### Attributes
    - `lock`: `threading.Lock` that threads writing to `ressource` should abide.
    - `ressource`

    """

    def __init__(self, ressource):
        self.lock: Lock = Lock()
        self.ressource = ressource

    def __enter__(self):
        """Lock `ressource` and return it."""
        self.lock.acquire()
        return self.ressource

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        """Release the lock."""
        self.lock.release()


def get_available_ip_addresses() -> list:
    """Return a list of all locally available IPv4 addresses."""
    addresses = []
    for adapter in ifaddr.get_adapters():
        for ip_addr in adapter.ips:
            if ip_addr.is_IPv4 and ip_addr.ip[:3] in {"10.", "172", "192", "127"}:
                # only local IPv4 addresses
                addresses.append(ip_addr.ip)
    return addresses
