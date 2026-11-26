from datetime import datetime, timezone


def utc(value: datetime | None):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _rounded(value, digits=2):
    return round(value, digits) if value is not None else None


def dataset_view(dataset, include_rows=False):
    item = {
        "id": dataset.id, "name": dataset.name, "count": len(dataset.rows),
        "checksum": dataset.checksum, "author": dataset.author, "created_at": utc(dataset.created_at),
    }
    if include_rows:
        item["rows"] = dataset.rows
    return item


def run_view(run, include_result=False, version=None):
    item = {
        "id": run.id, "dataset_id": run.dataset_id, "label": run.label, "parameter": run.parameter,
        "status": run.status, "error": run.error, "actor": run.actor, "model_version": version,
        "created_at": utc(run.created_at), "started_at": utc(run.started_at),
        "finished_at": utc(run.finished_at),
    }
    if include_result:
        item["result"] = run.result
    return item


def version_view(version, names=None):
    rival = None
    if version.rival_id:
        rival = {
            "id": version.rival_id,
            "name": (names or {}).get(version.rival_id, "—"),
            "mae": _rounded(version.rival_mae),
            "exceeded": version.rival_exceeded,
        }
    return {
        "id": version.id, "name": version.label, "state": version.state,
        "dataset_id": version.dataset_id, "actor": version.actor,
        "buffer": _rounded(version.buffer, 1),
        "audit_mae": _rounded(version.audit_mae),
        "audit_exceeded": version.audit_exceeded, "audit_count": version.audit_count,
        "train_count": version.train_count, "calibration_count": version.calibration_count,
        "rival": rival, "error": version.error,
        "created_at": utc(version.created_at), "finished_at": utc(version.finished_at),
    }


def review_view(review):
    return {
        "id": review.id, "run_id": review.run_id, "decision": review.decision,
        "samples": review.samples, "note": review.note, "reviewer": review.reviewer,
        "created_at": utc(review.created_at),
    }


def audit_view(event):
    return {"actor": event.actor, "action": event.action, "subject": event.subject, "created_at": utc(event.created_at)}
