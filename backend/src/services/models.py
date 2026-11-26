"""Versioned duration models: bootstrap, candidate trials, and guarded switches."""

import logging
import pickle
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from src.business.algorithm import partition
from src.business.estimator import DurationFit, check_cohorts
from src.config.settings import ARTIFACTS, Session
from src.constants.workflow import ModelStage
from src.models.base import utcnow
from src.models.dataset import Dataset
from src.models.model_version import ModelRegistry, ModelVersion
from src.schemas.resources import version_view
from src.services import datasets
from src.services.audit import record
from src.services.notify import wake

log = logging.getLogger(__name__)
LEASE = timedelta(minutes=10)
MAX_ATTEMPTS = 3
REGISTRY_ID = 1


def _artifact_path(version_id):
    return ARTIFACTS / "models" / f"{version_id}.pkl"


def dump_fit(version_id, fit):
    path = _artifact_path(version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(pickle.dumps({"model": fit.model, "buffer": fit.buffer}))
    temporary.replace(path)
    return str(path.relative_to(ARTIFACTS))


def load_fit(version):
    if not version.artifact:
        raise ValueError(f"模型版本 {version.label} 缺少模型文件。")
    path = ARTIFACTS / version.artifact
    if not path.is_file():
        raise ValueError(f"模型版本 {version.label} 的模型文件缺失。")
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    return DurationFit(payload["model"], payload["buffer"])


def lock_registry(db):
    registry = db.get(ModelRegistry, REGISTRY_ID, with_for_update=True)
    if registry is None:
        registry = ModelRegistry(id=REGISTRY_ID)
        db.add(registry)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            registry = db.get(ModelRegistry, REGISTRY_ID, with_for_update=True)
    return registry


def _fill_metrics(version, fit, groups, audit):
    version.buffer = fit.buffer
    version.audit_mae, version.audit_exceeded, version.audit_count = audit
    version.train_count = len(groups["训练"])
    version.calibration_count = len(groups["校准"])


def ensure_bootstrap(db, dataset, actor):
    """首版：没有在用版时，用已有完工记录照原法同步训练并校准，直接启用。"""
    registry = lock_registry(db)
    if registry.in_use_id:
        return db.get(ModelVersion, registry.in_use_id)
    groups = partition(dataset.rows)
    fit = DurationFit.train(groups["训练"], groups["校准"], groups["核验"])
    version = ModelVersion(
        serial=registry.next_serial, dataset_id=dataset.id, actor=actor,
        state=ModelStage.IN_USE.value, finished_at=utcnow(),
    )
    registry.next_serial += 1
    _fill_metrics(version, fit, groups, fit.assess(groups["核验"]))
    db.add(version)
    db.flush()
    version.artifact = dump_fit(version.id, fit)
    registry.in_use_id = version.id
    record(db, actor, "model_promoted", version.id)
    return version


def request_trial(dataset_id, actor):
    with Session.begin() as db:
        dataset = datasets.require(db, dataset_id)
        try:
            groups = partition(dataset.rows)
            check_cohorts(groups["训练"], groups["校准"], groups["核验"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        busy = db.scalar(select(ModelVersion).where(
            ModelVersion.dataset_id == dataset_id,
            ModelVersion.state.in_([ModelStage.PENDING.value, ModelStage.TRIALING.value]),
        ))
        if busy is not None:
            raise HTTPException(409, "该数据版本已有候选试算在进行。")
        registry = lock_registry(db)
        version = ModelVersion(serial=registry.next_serial, dataset_id=dataset.id, actor=actor)
        registry.next_serial += 1
        db.add(version)
        db.flush()
        record(db, actor, "model_queued", version.id)
        response = version_view(version)
    wake(version.id)
    return response


def list_versions():
    with Session() as db:
        rows = list(db.scalars(select(ModelVersion).order_by(ModelVersion.serial.desc())))
        names = {row.id: row.label for row in rows}
        return [version_view(row, names) for row in rows]


def ref(version):
    return {"id": version.id, "name": version.label, "state": version.state}


def refs_for(db, version_ids):
    ids = {version_id for version_id in version_ids if version_id}
    if not ids:
        return {}
    rows = db.scalars(select(ModelVersion).where(ModelVersion.id.in_(ids)))
    return {row.id: ref(row) for row in rows}


def load_version(version_id):
    with Session() as db:
        version = db.get(ModelVersion, version_id)
        if version is None:
            raise ValueError("计算单锁定的模型版本不存在。")
        return version, load_fit(version)


def provenance(version):
    return {
        "train_count": version.train_count,
        "calibration_count": version.calibration_count,
        "audit_mae": version.audit_mae,
        "audit_exceeded": version.audit_exceeded,
        "audit_count": version.audit_count,
    }


def claim_trial():
    expired = utcnow() - LEASE
    stale = and_(ModelVersion.state == ModelStage.TRIALING.value, ModelVersion.started_at < expired)
    available = or_(ModelVersion.state == ModelStage.PENDING.value, stale)
    failed_ids = []
    with Session.begin() as db:
        exhausted = db.scalars(
            select(ModelVersion).where(stale, ModelVersion.attempts >= MAX_ATTEMPTS).with_for_update(skip_locked=True)
        )
        for version in exhausted:
            version.state = ModelStage.FAILED.value
            version.error = "候选试算多次中断。请重新提交试算。"
            version.finished_at = utcnow()
            record(db, "worker", "model_failed", version.id)
            failed_ids.append(version.id)
        version = db.scalar(
            select(ModelVersion).where(available, ModelVersion.attempts < MAX_ATTEMPTS)
            .order_by(ModelVersion.created_at, ModelVersion.id).limit(1).with_for_update(skip_locked=True)
        )
        job = None
        if version is not None:
            version.state = ModelStage.TRIALING.value
            version.started_at = utcnow()
            version.attempts += 1
            dataset = db.get(Dataset, version.dataset_id)
            job = (version.id, dataset.rows)
    for version_id in failed_ids:
        _artifact_path(version_id).unlink(missing_ok=True)
    return job


def run_trial(job):
    version_id, rows = job
    try:
        groups = partition(rows)
        fit = DurationFit.train(groups["训练"], groups["校准"], groups["核验"])
        audit = fit.assess(groups["核验"])
        artifact = dump_fit(version_id, fit)
    except ValueError as exc:
        fail_trial(version_id, str(exc))
        return
    except Exception:
        log.exception("Trial %s failed", version_id)
        fail_trial(version_id, "候选训练或评估失败。请检查数据后重试。")
        return
    try:
        with Session.begin() as db:
            registry = lock_registry(db)
            candidate = db.get(ModelVersion, version_id, with_for_update=True)
            if candidate is None or candidate.state != ModelStage.TRIALING.value:
                return
            incumbent = db.get(ModelVersion, registry.in_use_id) if registry.in_use_id else None
            rival = None
            if incumbent is not None and incumbent.id != candidate.id:
                # 锁定期间以当前在用版为准：试算期间在用版更换过的，按新版重新比较。
                rival_fit = load_fit(incumbent)
                rival = rival_fit.assess(groups["核验"])
                candidate.rival_id = incumbent.id
                candidate.rival_mae, candidate.rival_exceeded = rival[0], rival[1]
            _fill_metrics(candidate, fit, groups, audit)
            candidate.artifact = artifact
            candidate.finished_at = utcnow()
            if rival is None or (audit[0] < rival[0] and audit[1] <= rival[1]):
                if incumbent is not None:
                    incumbent.state = ModelStage.RETIRED.value
                candidate.state = ModelStage.IN_USE.value
                registry.in_use_id = candidate.id
                record(db, "worker", "model_promoted", candidate.id)
            else:
                candidate.state = ModelStage.REJECTED.value
                record(db, "worker", "model_rejected", candidate.id)
    except Exception:
        # 切换失败保留旧版：事务回滚，注册表仍指向原在用版。
        log.exception("Trial %s switch failed", version_id)
        fail_trial(version_id, "版本切换失败，已保留在用版本。请重新提交试算。")


def fail_trial(version_id, error):
    try:
        with Session.begin() as db:
            change = db.execute(
                update(ModelVersion)
                .where(ModelVersion.id == version_id, ModelVersion.state == ModelStage.TRIALING.value)
                .values(state=ModelStage.FAILED.value, error=error, finished_at=utcnow())
            )
            failed = bool(change.rowcount)
            if failed:
                record(db, "worker", "model_failed", version_id)
    except Exception:
        log.exception("Marking trial %s as failed errored", version_id)
        return
    if failed:
        _artifact_path(version_id).unlink(missing_ok=True)
