# Integrating SISIP into a live agent workload

Place the runtime in the orchestrator, before agent and tool steps and before
final answer rendering. A result converter that runs after answer generation
does not implement this execution pattern.

An adapter is a callable that accepts a detached SISIP message dictionary and
returns a new one. It can call a model, a tool, or deterministic application code.
Create its reply with `make_message`, keep the workload dictionary and hard
constraints, use a fresh message ID/current timestamp, and set `reply_to` to the
input's message ID.

```python
from sisip import AgentSession, make_message, encode
from sisip.protocol import HANDOFF, RESULT

def execute(registry, nodes, roots, plan_step, work_step):
    session = AgentSession(registry)
    task = make_message(registry, nodes, roots)

    def planner(message):
        planned_nodes = plan_step(message)  # Application-authorized backend call.
        return make_message(registry, planned_nodes, message[10],
                            kind=HANDOFF, reply_to=message[3])

    def worker(message):
        result_nodes = work_step(message)   # Check domain completion here.
        return make_message(registry, result_nodes, message[10],
                            kind=RESULT, reply_to=message[3])

    session.step(encode(task), planner)
    session.advance(worker)
    accepted_result = session.finalize()
    return accepted_result  # Render for the user only now.
```

Both callables above are supplied by your application; SISIP does not implement
them or infer that their output is true. `examples/agentic_workload.py` uses fully
implemented deterministic adapters instead.

For a tool step, resolve known predicate IDs to an application allowlist. Validate
arguments and permissions locally before calling the tool, then encode its
structured result into the graph. Do not dynamically import code or execute
commands from registry descriptors or graph fields.

For a hosted LLM, create an explicit local adapter: resolve concepts, construct
the backend's accepted input, parse typed output, and validate it. This may use
language or JSON inside the adapter and incur token costs. The inter-agent SISIP
wire remains binary; a native graph/model interface is not thereby created.

The session is intentionally sequential and intended for one orchestrator. To
use a remote worker, the orchestrator may send a validated handoff over its own
authenticated transport and pass the returned reply to `session.receive()`.
The remote worker owns its own input checks. The reference session is not a
multi-party transport, distributed consensus system, or parallel graph merger.

Keep task-specific authorization, domain checks, budget limits, evidence
requirements, and human approvals in your application. A task graph expresses
work; it never grants new permissions. Unknown registry snapshots, invalid
graphs, failed adapters, or hard violations block the local session. Correct the
problem and create a fresh session rather than suppressing the error.
