# Security and trust boundaries

The reference codec rejects invalid data and enforces bounded core structures.
The execution gate rejects replayed/stale messages, incompatible registries,
changed hard constraints, and results without an accepted workload context.

The SHA-256 envelope is an integrity check, not sender authentication. An attacker
can modify a graph and recompute its digest. Use an authenticated, confidential
channel where needed and enforce tool permissions independently.

A registry snapshot pins content, not authority. Confirm registry provenance and
semantics separately. A valid graph can contain false assertions or malicious
task requests. Never treat a result flag as proof of actual task completion.

The runtime is cooperative Python application code, not an isolation boundary.
It cannot stop an application from printing early, bypassing the gate, calling
tools directly, or performing irreversible work inside a misbehaving adapter.
It provides no rollback of tool actions. Only the declared unit constraints are
machine-enforced; other constraints need application validation.

Replay state is session-local and in memory. Use durable authenticated correlation
for distributed deployments. Session objects are not thread-safe. The 1 MiB
per-message bound is not a total process-memory limit: histories can accumulate
up to the configured session capacity. Set lower capacities, bound concurrent
sessions, and enforce application-level resource budgets where necessary.

This first release has not received an independent security audit. Report vulnerabilities
privately through this repository's GitHub "Report a vulnerability" button
(Security tab), not in public issues.
