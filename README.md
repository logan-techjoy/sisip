# Super Intelligence Semantic Interchange Protocol

**SISIP v1.0 — structured semantic exchange during agentic workload execution.**

SISIP carries task graphs, constraints, intermediate state, and results between
agent adapters while work is running. A runtime checks each exchange before the
next adapter runs and opens a final-output boundary only after an accepted result.

This release contains an executable Python reference implementation and a proposed
v1.0 core specification. “Super Intelligence” is the protocol's name, not a claim
that this package creates superintelligence or provides access to private model reasoning.

## Quick start

Python 3.10 or newer. The core has no third-party runtime dependencies.

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/agentic_workload.py
sisip demo
sisip example temperature.sisip
sisip inspect temperature.sisip
```

The demo uses deterministic planner and worker adapters, with no API keys or
network calls. It validates a supplied observation; it does not fetch weather.

## What happens during execution

1. The orchestrator creates a typed task graph using a shared registry snapshot.
2. SISIP verifies the message, resolves its concepts, and checks unit constraints.
3. The planner adapter receives the graph and returns a handoff graph.
4. The runtime validates that handoff before the worker adapter runs.
5. The worker returns a result graph. Hard constraints must remain intact.
6. The orchestrator calls `finalize()` before rendering a human-facing answer.

```python
from sisip import AgentSession, encode
from sisip.demo import DEMO_REGISTRY, example_message

# planner_adapter and worker_adapter are application-supplied callables.
# Each receives a detached graph and returns a new SISIP message dictionary.
def execute(task, planner_adapter, worker_adapter, clock=None):
    session = AgentSession(DEMO_REGISTRY, clock=clock)
    session.step(encode(task), planner_adapter)
    session.advance(worker_adapter)
    return session.finalize()  # Render an answer only after this succeeds.
```

See [the complete runnable example](examples/agentic_workload.py) and
[adapter integration](docs/ADAPTERS.md). Use current timestamps for live work;
the committed conformance fixture intentionally uses a fixed historical timestamp.

## Implemented in v1.0

- A strict deterministic subset of CBOR with no text, floats, or model token IDs.
- SHA-256 concept identities, local numeric handles, and pinned registry snapshots.
- Entity, concept, exact decimal quantity, interval, statement, and unit-constraint nodes.
- Asserted/hypothetical statements and nullable fixed-point sender confidence.
- Whole-payload integrity verification, schema/reference checking, and role resolution.
- A sequential execution session with replay/time checks, persistent hard constraints,
  and a final-output gate. Sessions are local orchestration state, not a network transport.
- Diagnostic CLI, tests, binary conformance fixture, and GitHub Actions configuration.

## Scope and limits

Concept identifiers make references stable; shared definitions and tested adapters
make them useful. Hashing a descriptor does not cause two models to understand it.
This release does not implement LLM inference, training, embedding translation,
general theorem proving, probabilistic inference, or a universal ontology.

The implemented hard constraint is **exact required-unit identity**. The runtime
does not infer conversions, temperature trends, task completeness, or factual truth.
Applications must validate domain-specific task success before returning `RESULT`.
The gate is cooperative application control, not a sandbox around arbitrary Python
or a mandatory hook inside a hosted model.

The digest detects changed bytes; it does not authenticate a sender. Supply an
authenticated channel and application authorization for remote use. Signatures,
compression, deltas, conditional logic, and parallel workload merging are future
profiles, not implemented capabilities.

## Documentation

- [Revised SISIP v1.0 specification](docs/SISIP_v1.0.md)
- [Machine-readable core schema](docs/core.cddl)
- [Agent adapter integration](docs/ADAPTERS.md)
- [Changes from the supplied SIP draft](CHANGELOG.md)
- [Security and trust boundaries](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE). The
`sisip-core` package name has not been reserved on PyPI.
