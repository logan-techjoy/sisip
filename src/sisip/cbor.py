"""Strict SISIP subset of RFC 8949 deterministic CBOR, not a general codec."""

MAX_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_ITEMS = 100_000


class ProtocolError(ValueError):
    """Malformed, noncanonical, unsupported, or invalid SISIP data."""


def _head(major, value):
    if not 0 <= value <= 0xffffffffffffffff:
        raise ProtocolError("integer outside CBOR 64-bit argument range")
    prefix = major << 5
    if value < 24:
        return bytes([prefix | value])
    for width, ai in ((1, 24), (2, 25), (4, 26), (8, 27)):
        if value < 1 << (width * 8):
            return bytes([prefix | ai]) + value.to_bytes(width, "big")
    raise ProtocolError("invalid integer")


def dumps(value):
    """Encode integers, bytes, lists, integer-keyed maps, and null only."""
    count = 0
    output = bytearray()

    def emit(chunk):
        if len(output) + len(chunk) > MAX_BYTES:
            raise ProtocolError("message exceeds byte limit")
        output.extend(chunk)

    def encode(obj, depth):
        nonlocal count
        count += 1
        if depth > MAX_DEPTH or count > MAX_ITEMS:
            raise ProtocolError("CBOR resource limit exceeded")
        if obj is None:
            emit(b"\xf6")
        elif type(obj) is int:
            emit(_head(0, obj) if obj >= 0 else _head(1, -1 - obj))
        elif type(obj) is bytes:
            if len(obj) > MAX_BYTES:
                raise ProtocolError("byte string too large")
            emit(_head(2, len(obj)))
            emit(obj)
        elif type(obj) is list:
            if len(obj) > MAX_ITEMS:
                raise ProtocolError("array too large")
            emit(_head(4, len(obj)))
            for item in obj:
                encode(item, depth + 1)
        elif type(obj) is dict:
            if len(obj) > MAX_ITEMS or any(type(k) is not int for k in obj):
                raise ProtocolError("map requires integer keys and bounded size")
            pairs = [(_head(0, k) if k >= 0 else _head(1, -1-k), k, v)
                     for k, v in obj.items()]
            pairs.sort(key=lambda pair: pair[0])
            emit(_head(5, len(pairs)))
            for _, key, val in pairs:
                encode(key, depth + 1)
                encode(val, depth + 1)
        else:
            raise ProtocolError("unsupported CBOR type (text, floats, booleans, tags prohibited)")

    encode(value, 0)
    return bytes(output)


def loads(data):
    """Reject duplicate keys, nonminimal integers, trailing bytes, and excess nesting."""
    if type(data) is not bytes or len(data) > MAX_BYTES:
        raise ProtocolError("expected bounded bytes")
    pos = 0
    count = 0

    def take(n):
        nonlocal pos
        if pos + n > len(data):
            raise ProtocolError("truncated CBOR")
        out = data[pos:pos+n]
        pos += n
        return out

    def decode(depth):
        nonlocal count
        count += 1
        if depth > MAX_DEPTH or count > MAX_ITEMS:
            raise ProtocolError("CBOR resource limit exceeded")
        first = take(1)[0]
        major, ai = first >> 5, first & 31
        if major == 7 and ai == 22:
            return None
        if major not in (0, 1, 2, 4, 5):
            raise ProtocolError("unsupported CBOR major/simple type")
        if ai < 24:
            n = ai
        elif ai in (24, 25, 26, 27):
            width = {24: 1, 25: 2, 26: 4, 27: 8}[ai]
            n = int.from_bytes(take(width), "big")
            if n < {24: 24, 25: 256, 26: 65536, 27: 4294967296}[ai]:
                raise ProtocolError("nonminimal CBOR argument")
        else:
            raise ProtocolError("indefinite/reserved CBOR argument prohibited")
        if major == 0:
            return n
        if major == 1:
            return -1 - n
        if major == 2:
            return take(n)
        if n > MAX_ITEMS:
            raise ProtocolError("container item limit exceeded")
        if major == 4:
            return [decode(depth + 1) for _ in range(n)]
        out = {}
        previous = None
        for _ in range(n):
            start = pos
            key = decode(depth + 1)
            raw_key = data[start:pos]
            if type(key) is not int:
                raise ProtocolError("map key must be integer")
            if previous is not None and raw_key <= previous:
                raise ProtocolError("duplicate or noncanonical map key")
            previous = raw_key
            out[key] = decode(depth + 1)
        return out

    value = decode(0)
    if pos != len(data):
        raise ProtocolError("trailing CBOR bytes")
    return value
