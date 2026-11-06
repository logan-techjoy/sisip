"""SISIP 1.0 core graph schema, exact encoding, and integrity envelope."""
from hashlib import sha256
from hmac import compare_digest
from time import time
from uuid import uuid4
from .cbor import dumps, loads, ProtocolError

MAGIC = 0x5349534950
TASK, UPDATE, RESULT, HANDOFF = range(4)
ENTITY, QUANTITY, STATEMENT, INTERVAL, CONCEPT, CONSTRAINT = range(6)
ASSERTED, HYPOTHESIS = range(2)
HARD, SOFT = range(2)


def _need(condition, message):
    if not condition:
        raise ProtocolError(message)


def _uint(value):
    return type(value) is int and 0 <= value <= 0xffffffffffffffff


def _array(value, length=None):
    return type(value) is list and (length is None or len(value) == length)


def _bytes(value, length):
    return type(value) is bytes and len(value) == length


def validate(message):
    """Validate syntax/references; ontology support and constraints are separate."""
    m = message
    _need(type(m) is dict and all(type(k) is int for k in m) and set(m) == set(range(12)),
          "payload must have exactly integer keys 0..11")
    _need(m[0] == MAGIC and type(m[0]) is int, "wrong protocol identifier")
    _need(_array(m[1], 2) and all(type(v) is int for v in m[1]) and m[1] == [1, 0],
          "unsupported version")
    _need(type(m[2]) is int and m[2] == 0, "unsupported profile")
    _need(_bytes(m[3], 16), "message ID must be 16 bytes")
    _need(_uint(m[4]), "timestamp must be unsigned milliseconds")
    _need(type(m[5]) is int and m[5] in range(4), "unsupported message kind")
    _need(m[6] is None or _bytes(m[6], 16), "invalid reply ID")
    _need(_bytes(m[7], 32), "snapshot must be 32 bytes")
    _need(_array(m[8]) and len(m[8]) <= 4096, "invalid concept dictionary")
    concepts = {}
    previous = 0
    for entry in m[8]:
        _need(_array(entry, 2), "invalid dictionary entry")
        handle, cid = entry
        _need(_uint(handle) and handle > previous and _bytes(cid, 32),
              "dictionary handles must increase; IDs must be 32 bytes")
        concepts[handle] = cid
        previous = handle
    _need(len(set(concepts.values())) == len(concepts), "duplicate concept ID")
    _need(_array(m[9]) and 0 < len(m[9]) <= 4096, "invalid node array")
    nodes = {}
    previous = 0
    for node in m[9]:
        _need(_array(node, 3), "invalid node record")
        nid, kind, data = node
        _need(_uint(nid) and nid > previous, "node IDs must be positive and increasing")
        _need(type(kind) is int and kind in range(6), "unsupported node type")
        nodes[nid] = (kind, data)
        previous = nid

    used = set()

    def concept(handle):
        _need(_uint(handle) and handle in concepts, "unknown concept handle")
        used.add(handle)

    def node_ref(nid):
        _need(_uint(nid) and nid in nodes, "dangling node reference")

    for nid, (kind, data) in nodes.items():
        if kind in (ENTITY, CONCEPT):
            concept(data)
        elif kind == QUANTITY:
            _need(_array(data, 3), "quantity requires mantissa, exponent, unit")
            mantissa, exponent, unit = data
            _need(type(mantissa) is int and -(1 << 63) <= mantissa < (1 << 63),
                  "quantity mantissa outside int64")
            _need(type(exponent) is int and -18 <= exponent <= 18, "invalid exponent")
            _need((mantissa == 0 and exponent == 0) or
                  (mantissa != 0 and (mantissa % 10 != 0 or exponent == 18)),
                  "decimal is not normalized")
            concept(unit)
        elif kind == STATEMENT:
            _need(_array(data, 5), "statement requires subject, predicate, object, modality, confidence")
            subject, predicate, obj, modality, confidence = data
            node_ref(subject)
            node_ref(obj)
            concept(predicate)
            _need(type(modality) is int and modality in range(2), "unsupported modality")
            _need(confidence is None or (_uint(confidence) and confidence <= 10000),
                  "confidence must be null or integer 0..10000")
        elif kind == INTERVAL:
            _need(_array(data, 2) and all(_uint(x) for x in data) and data[0] <= data[1],
                  "interval requires ordered unsigned epoch milliseconds")
        elif kind == CONSTRAINT:
            _need(_array(data, 3), "constraint requires target, required unit, strength")
            target, unit, strength = data
            node_ref(target)
            _need(nodes[target][0] == QUANTITY, "unit constraint target must be quantity")
            concept(unit)
            _need(type(strength) is int and strength in range(2), "invalid constraint strength")

    for key in (10, 11):
        _need(_array(m[key]) and all(_uint(x) for x in m[key]), "invalid root/required array")
        _need(m[key] == sorted(set(m[key])), "root/required arrays must be sorted and unique")
    _need(bool(m[10]), "at least one root is required")
    for nid in m[10]:
        node_ref(nid)
        _need(nodes[nid][0] in (STATEMENT, CONSTRAINT), "roots must be statements or constraints")
    for nid, (kind, _) in nodes.items():
        if kind == CONSTRAINT:
            _need(nid in m[10], "constraints must be explicit roots")
    for handle in m[11]:
        concept(handle)
    _need(used == set(concepts), "unused concept dictionary entry")
    return m


def make_message(registry, nodes, roots, *, kind=TASK, reply_to=None,
                 message_id=None, timestamp_ms=None, required=None):
    """Construct a core message using a pinned local registry."""
    required = [] if required is None else sorted(set(required))
    used = set(required)
    for _, ntype, data in nodes:
        if ntype in (ENTITY, CONCEPT):
            used.add(data)
        elif ntype == QUANTITY and _array(data, 3):
            used.add(data[2])
        elif ntype == STATEMENT and _array(data, 5):
            used.add(data[1])
        elif ntype == CONSTRAINT and _array(data, 3):
            used.add(data[1])
    _need(all(_uint(h) for h in used), "invalid concept handle")
    # Only referenced/required handles are sent; handles stay registry-assigned.
    dictionary = registry.dictionary(used)
    m = {
        0: MAGIC, 1: [1, 0], 2: 0,
        3: uuid4().bytes if message_id is None else message_id,
        4: int(time() * 1000) if timestamp_ms is None else timestamp_ms,
        5: kind, 6: reply_to, 7: registry.snapshot, 8: dictionary,
        9: sorted(nodes, key=lambda n: n[0]), 10: sorted(roots),
        11: required,
    }
    return validate(m)


def encode(message):
    payload = dumps(validate(message))
    digest = sha256(b"SISIP/1.0\x00" + payload).digest()
    return dumps([payload, digest])


def decode(wire):
    envelope = loads(wire)
    _need(_array(envelope, 2) and type(envelope[0]) is bytes and _bytes(envelope[1], 32),
          "invalid integrity envelope")
    payload, digest = envelope
    _need(compare_digest(sha256(b"SISIP/1.0\x00" + payload).digest(), digest),
          "payload digest mismatch")
    return validate(loads(payload))


def digest(message):
    """Return the domain-separated payload digest."""
    return sha256(b"SISIP/1.0\x00" + dumps(validate(message))).digest()
