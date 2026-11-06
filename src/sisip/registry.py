"""Local, version-pinned concept definitions; no global registry is implied."""
from dataclasses import dataclass
from hashlib import sha256
from .cbor import dumps, ProtocolError

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
        record = dumps([self.kind, self.descriptor.encode("utf-8")])
        return sha256(b"SISIP-CONCEPT/1\x00" + record).digest()


class Registry:
    def __init__(self, concepts=()):
        self._concepts = {}
        for concept in concepts:
            cid = concept.cid
            if cid in self._concepts and self._concepts[cid] != concept:
                raise ProtocolError("concept identity collision")
            self._concepts[cid] = concept

    @property
    def snapshot(self):
        return sha256(b"SISIP-REGISTRY/1\x00" + dumps(sorted(self._concepts))).digest()

    def get(self, cid):
        return self._concepts.get(cid)

    def dictionary(self):
        return [[i, cid] for i, cid in enumerate(sorted(self._concepts), 1)]

    def handle(self, concept):
        for handle, cid in self.dictionary():
            if cid == concept.cid:
                return handle
        raise KeyError(concept.descriptor)
