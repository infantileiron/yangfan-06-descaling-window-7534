from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.workflow import ModelStage
from src.models.base import Base, new_id, utcnow


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    serial: Mapped[int] = mapped_column(unique=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    state: Mapped[str] = mapped_column(String(20), default=ModelStage.PENDING.value, index=True)
    buffer: Mapped[float | None] = mapped_column(Float, nullable=True)
    audit_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    audit_exceeded: Mapped[int | None] = mapped_column(nullable=True)
    audit_count: Mapped[int | None] = mapped_column(nullable=True)
    train_count: Mapped[int | None] = mapped_column(nullable=True)
    calibration_count: Mapped[int | None] = mapped_column(nullable=True)
    rival_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rival_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    rival_exceeded: Mapped[int | None] = mapped_column(nullable=True)
    artifact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(160))
    attempts: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def label(self) -> str:
        return f"V{self.serial}"


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    in_use_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    next_serial: Mapped[int] = mapped_column(default=1)
