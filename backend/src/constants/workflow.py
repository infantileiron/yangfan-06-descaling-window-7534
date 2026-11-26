from enum import Enum


class Role(str, Enum):
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Stage(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ModelStage(str, Enum):
    PENDING = "pending"
    TRIALING = "trialing"
    IN_USE = "in_use"
    RETIRED = "retired"
    REJECTED = "rejected"
    FAILED = "failed"


class Decision(str, Enum):
    APPROVE = "approve"
    HOLD = "hold"
