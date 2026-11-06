"""Deterministic test fixture; illustrative local vocabulary, not a universal ontology."""
from copy import deepcopy
from .registry import Concept, Registry, ENTITY, PREDICATE, UNIT
from .protocol import make_message, HANDOFF, RESULT
from .runtime import AgentSession

LOCATION = Concept("sisip.demo/v1/entity/Joplin-Missouri-USA", ENTITY)
DELTA = Concept("sisip.demo/v1/predicate/temperature-difference-unspecified-period", PREDICATE)
CELSIUS_DELTA = Concept("sisip.demo/v1/unit/degree-Celsius-difference", UNIT)
DEMO_REGISTRY = Registry([LOCATION, DELTA, CELSIUS_DELTA])


def example_message(*, timestamp_ms=1735689600000):
    r = DEMO_REGISTRY
    unit = r.handle(CELSIUS_DELTA)
    return make_message(r, [
        [1, 0, r.handle(LOCATION)],
        [2, 1, [5, 0, unit]],
        [3, 2, [1, r.handle(DELTA), 2, 0, 8200]],
        [4, 5, [2, unit, 0]],
    ], [3, 4], timestamp_ms=timestamp_ms, message_id=bytes.fromhex("00000000000000000000000000000001"))


def run_demo(*, timestamp_ms=1735689600000):
    """Two deterministic adapters exchange a graph while the workload is running.

    The worker checks an already supplied observation; it does not measure weather
    or demonstrate a real model's semantic alignment.
    """
    r = DEMO_REGISTRY
    session = AgentSession(r, clock=lambda: timestamp_ms)

    def planner(graph):
        return make_message(r, deepcopy(graph[9]), graph[10], kind=HANDOFF,
                            reply_to=graph[3], message_id=bytes.fromhex("00" * 15 + "02"),
                            timestamp_ms=timestamp_ms)

    def worker(graph):
        quantity = next(n for n in graph[9] if n[0] == 2)
        if quantity[2] != [5, 0, r.handle(CELSIUS_DELTA)]:
            raise ValueError("unexpected task observation")
        return make_message(r, deepcopy(graph[9]), graph[10], kind=RESULT,
                            reply_to=graph[3], message_id=bytes.fromhex("00" * 15 + "03"),
                            timestamp_ms=timestamp_ms)

    from .protocol import encode
    session.step(encode(example_message(timestamp_ms=timestamp_ms)), planner)
    session.advance(worker)
    final_graph = session.finalize()
    return final_graph, session.history
