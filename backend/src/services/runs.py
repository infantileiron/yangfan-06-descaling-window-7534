from fastapi import HTTPException
from sqlalchemy import select

from src.business.profile import PROFILE
from src.config.settings import Session
from src.models.run import Run
from src.schemas.resources import run_view
from src.services import datasets, models
from src.services.audit import record
from src.services.notify import wake


def require(db, run_id):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "计算单不存在。")
    return run


def list_runs():
    with Session() as db:
        rows = list(db.scalars(select(Run).order_by(Run.created_at.desc(), Run.id.desc())))
        versions = models.refs_for(db, [run.model_version_id for run in rows])
        return [run_view(run, version=versions.get(run.model_version_id)) for run in rows]


def version_ref(db, run):
    return models.refs_for(db, [run.model_version_id]).get(run.model_version_id)


def submit(body, actor):
    control = PROFILE["parameter"]
    if not control["min"] <= body.parameter <= control["max"]:
        raise HTTPException(422, f"「{control['label']}」超出允许范围。")
    with Session.begin() as db:
        dataset = datasets.require(db, body.dataset_id)
        try:
            version = models.ensure_bootstrap(db, dataset, actor)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        run = Run(
            dataset_id=body.dataset_id, label=body.label, parameter=body.parameter,
            actor=actor, model_version_id=version.id,
        )
        db.add(run)
        db.flush()
        record(db, actor, "run_queued", run.id)
        response = run_view(run, version=models.ref(version))
    wake(run.id)
    return response
