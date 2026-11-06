"""Local, version-pinned concept definitions; no global registry is implied."""
from dataclasses import dataclass
from hashlib import sha256
from .cbor import dumps, ProtocolError, _head

ENTITY, CLASS, PREDICATE, UNIT = range(4)


@dataclass(frozen=True)
class Concept:
    descriptor: str
    kind: int

    @property
    def cid(self):
        if type(self.descriptor) is not str or not self.descriptor:
            raise ProtocolError("concept descriptor must be nonempty text")
        if type(self.kind) is not int or self.kind not in range(4):
            raise ProtocolError("invalid registry kind")
        try:
            encoded = self.descriptor.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProtocolError("concept descriptor must be valid Unicode text") from exc
        record = dumps([self.kind, encoded])
        return sha256(b"SISIP-CONCEPT/1\x00" + record).digest()


class Registry:
    def __init__(self, concepts=()):
        self._concepts = {}
        for concept in concepts:
            cid = concept.cid
            if cid in self._concepts and self._concepts[cid] != concept:
                raise ProtocolError("concept identity collision")
            self._concepts[cid] = concept
        self._ids = sorted(self._concepts)
        self._handles = {cid: i for i, cid in enumerate(self._ids, 1)}
        self._snapshot = None

    @property
    def snapshot(self):
        # Hash preimage, not a wire message: stream the deterministic CBOR array
        # (head + one 32-byte bstr per sorted ID) so the 1 MiB / 100k-item message
        # limits do not apply. Bytes equal dumps(sorted ids) for small registries.
        if self._snapshot is None:
            h = sha256(b"SISIP-REGISTRY/1\x00")
            h.update(_head(4, len(self._ids)))
            bstr_head = _head(2, 32)
            for cid in self._ids:
                h.update(bstr_head)
                h.update(cid)
            self._snapshot = h.digest()
        return self._snapshot

    def get(self, cid):
        return self._concepts.get(cid)

    def dictionary(self, handles=None):
        """Registry-assigned [handle, cid] pairs (1-based index into the sorted
        full registry). With `handles`, only those entries, in increasing order."""
        if handles is None:
            return [[i, cid] for i, cid in enumerate(self._ids, 1)]
        handles = set(handles)
        if not all(type(h) is int and 1 <= h <= len(self._ids) for h in handles):
            raise ProtocolError("handle not assigned by this registry")
        return [[h, self._ids[h - 1]] for h in sorted(handles)]

    def handle(self, concept):
        try:
            return self._handles[concept.cid]
        except KeyError:
            raise KeyError(concept.descriptor) from None
