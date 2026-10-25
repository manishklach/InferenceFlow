"""Private experiment readiness handshake; all timestamps use control-plane UTC."""
from sqlalchemy import select
from packages.common.db import Worker, WorkerProbe, now
from packages.common.identity import model_identity


def compatible(worker):
    return bool(worker and {name: getattr(worker, name) for name in model_identity()} == model_identity())


def consume(s, challenge):
    from packages.common.service import Problem
    # Match heartbeat/finalize lock order: wallet (caller), worker, then probe.
    worker_id = s.scalar(select(WorkerProbe.worker_id).where(WorkerProbe.id == challenge))
    worker = s.scalar(select(Worker).where(Worker.id == worker_id).with_for_update()) if worker_id else None
    probe = s.scalar(select(WorkerProbe).where(WorkerProbe.id == challenge).with_for_update())
    if (not worker or not compatible(worker) or not probe or probe.generation != worker.generation or not probe.completed_at
            or probe.expires_at <= now() or probe.consumed_at or worker.expires_at <= now()):
        raise Problem(503, "experiment_worker_not_ready", "Fresh single-use engine readiness proof required; no credits reserved.")
    probe.consumed_at = now()

