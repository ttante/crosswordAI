"""Source-backed knowledge graph primitives."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    source_pack_id: str
    name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    source_evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Relationship:
    id: str
    source_pack_id: str
    subject_id: str
    predicate: str
    object_id: str
    source_evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(slots=True)
class KnowledgeGraph:
    entities: dict[str, Entity] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.id] = entity

    def add_relationship(self, relationship: Relationship) -> None:
        if relationship.subject_id not in self.entities:
            raise ValueError(f"missing subject entity: {relationship.subject_id}")
        if relationship.object_id not in self.entities:
            raise ValueError(f"missing object entity: {relationship.object_id}")
        self.relationships.append(relationship)

    def related(self, entity_id: str, *, predicate: str | None = None) -> list[Entity]:
        found: list[Entity] = []
        for relationship in self.relationships:
            if relationship.subject_id != entity_id:
                continue
            if predicate is not None and relationship.predicate != predicate:
                continue
            found.append(self.entities[relationship.object_id])
        return found

    def clue_angles(self, entity_id: str) -> list[dict[str, object]]:
        angles: list[dict[str, object]] = []
        subject = self.entities[entity_id]
        for relationship in self.relationships:
            if relationship.subject_id == entity_id:
                obj = self.entities[relationship.object_id]
                angles.append(
                    {
                        "angle": f"{subject.name} -> {relationship.predicate} -> {obj.name}",
                        "subject_id": subject.id,
                        "object_id": obj.id,
                        "predicate": relationship.predicate,
                        "source_evidence_ids": list(relationship.source_evidence_ids),
                        "confidence": relationship.confidence,
                    }
                )
            elif relationship.object_id == entity_id:
                subj = self.entities[relationship.subject_id]
                angles.append(
                    {
                        "angle": f"{subj.name} -> {relationship.predicate} -> {subject.name}",
                        "subject_id": subj.id,
                        "object_id": subject.id,
                        "predicate": relationship.predicate,
                        "source_evidence_ids": list(relationship.source_evidence_ids),
                        "confidence": relationship.confidence,
                    }
                )
        return angles
