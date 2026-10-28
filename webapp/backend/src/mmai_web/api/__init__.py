"""Flask blueprints, one per service."""

from mmai_web.api import matching, notes, patients, pipeline, system, trials

BLUEPRINTS = [
    system.bp,
    notes.bp,
    patients.bp,
    trials.bp,
    matching.embedding_bp,
    matching.bp,
    pipeline.bp,
]
