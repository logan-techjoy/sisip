"""Validation gates for live agent steps, with explicit finalization."""
from copy import deepcopy
from dataclasses import dataclass
from time import time
from .cbor import ProtocolError
from .protocol import (decode, encode, digest, ENTITY, QUANTITY, STATEMENT,
                       CONCEPT, CONSTRAINT, HARD, RESULT)
from . import registry as roles


@dataclass(frozen=True)
class Assessment:
    message_id: bytes
    payload_digest: bytes
    missing_concepts: tuple
    hard_violations: tuple
    soft_violations: tuple

    @property
    def accepted(self):
        return not self.missing_concepts and not self.hard_violations


def assess(message, registry):
    """Resolve concepts and check the core unit constraints, without inference."""
    from .protocol import validate
    validate(message)
    concepts = dict(message[8])
    missing = tuple(sorted(cid for cid in concepts.values() if registry.get(cid) is None))
    hard, soft = [], []
    nodes = {n[0]: n[1:] for n in message[9]}

    def role(handle, expected):
        definition = registry.get(concepts[handle])
        if definition is not None and definition.kind != expected:
            raise ProtocolError("registry concept has incompatible role")

    for nid, (kind, data) in nodes.items():
        if kind == ENTITY:
            role(data, roles.ENTITY)
        elif kind == CONCEPT:
            role(data, roles.CLASS)
        elif kind == QUANTITY:
            role(data[2], roles.UNIT)
        elif kind == STATEMENT:
            role(data[1], roles.PREDICATE)
        elif kind == CONSTRAINT:
            target, unit, strength = data
            role(unit, roles.UNIT)
            if nodes[target][1][2] != unit:
                (hard if strength == HARD else soft).append(nid)
    return Assessment(message[3], digest(message), missing, tuple(hard), tuple(soft))


class AgentSession:
    """Single-workload gate. Caller owns transport authentication and tool policy.

    All unknown concepts block execution in the reference runtime, even if the
    sender did not mark them required. A blocked exchange terminates this session;
    correct the registry/graph and start a fresh workload session to retry.
    """

    def __init__(self, registry, *, max_age_ms=300_000, max_future_ms=30_000,
                 clock=None, max_messages=4096):
        if (type(max_age_ms) is not int or max_age_ms < 0 or
                type(max_future_ms) is not int or max_future_ms < 0 or
                type(max_messages) is not int or max_messages < 1):
            raise ValueError("session limits must be nonnegative integers; capacity must be positive")
        self.registry = registry
        self.max_age_ms = max_age_ms
        self.max_future_ms = max_future_ms
        self.clock = clock or (lambda: int(time() * 1000))
        self.max_messages = max_messages
        self._seen = set()
        self._blocked = False
        self._has_result = False
        self._closed = False
        self._in_step = False
        self._history = []

    @property
    def history(self):
        return tuple(deepcopy(self._history))

    def receive(self, wire):
        if self._closed or self._blocked:
            raise ProtocolError("session closed or blocked")
        try:
            m = decode(wire)
            now = self.clock()
            if not now - self.max_age_ms <= m[4] <= now + self.max_future_ms:
                raise ProtocolError("expired or future message")
            if m[3] in self._seen or len(self._seen) >= self.max_messages:
                raise ProtocolError("replayed message or session capacity exceeded")
            if not self._history:
                if m[5] != 0 or m[6] is not None:
                    raise ProtocolError("a workload must start with an unlinked task")
            else:
                previous = self._history[-1]
                if m[5] == 0 or m[6] != previous[3]:
                    raise ProtocolError("workload exchanges must reply to the latest message")
                if m[8] != previous[8]:
                    raise ProtocolError("workload concept dictionary changed")
                old_constraints = {n[0]: n for n in previous[9]
                                   if n[1] == CONSTRAINT and n[2][2] == HARD}
                new_nodes = {n[0]: n for n in m[9]}
                if any(new_nodes.get(nid) != node for nid, node in old_constraints.items()):
                    raise ProtocolError("workload dropped or changed a hard constraint")
            if m[7] != self.registry.snapshot:
                raise ProtocolError("registry snapshot mismatch")
            report = assess(m, self.registry)
            self._seen.add(m[3])
            self._history.append(deepcopy(m))
            if not report.accepted:
                self._blocked = True
            # A later update invalidates an earlier final result.
            self._has_result = report.accepted and m[5] == RESULT
            return deepcopy(m), report
        except Exception:
            self._blocked = True
            raise

    def step(self, incoming, handler):
        """Validate input BEFORE calling the adapter; validate its output too.

        Handler receives a detached graph and returns a message dictionary.
        It may consult models/tools through its own authorized integrations.
        """
        if self._in_step:
            raise ProtocolError("nested session steps are not supported")
        self._in_step = True
        try:
            message, report = self.receive(incoming)
            if not report.accepted:
                raise ProtocolError("unresolved concepts or hard constraints block adapter execution")
            return self._apply(message, handler)
        except Exception:
            self._blocked = True
            raise
        finally:
            self._in_step = False

    def _apply(self, message, handler):
        self._has_result = False
        outgoing = handler(deepcopy(message))
        if type(outgoing) is not dict or outgoing.get(6) != message[3]:
            raise ProtocolError("adapter output must reply to the input message")
        wire = encode(outgoing)
        _, output_report = self.receive(wire)
        if not output_report.accepted:
            raise ProtocolError("adapter output failed semantic checks")
        return wire

    def advance(self, handler):
        """Run the next adapter against the accepted current workload state."""
        if self._in_step or self._closed or self._blocked or not self._history:
            raise ProtocolError("cannot advance this session")
        self._in_step = True
        try:
            return self._apply(deepcopy(self._history[-1]), handler)
        except Exception:
            self._blocked = True
            raise
        finally:
            self._in_step = False

    def finalize(self):
        """Open the final-output boundary only after an accepted latest result."""
        if self._in_step or self._closed or self._blocked or not self._has_result:
            raise ProtocolError("final output blocked: no accepted latest result or failed workload")
        self._closed = True
        return deepcopy(self._history[-1])
