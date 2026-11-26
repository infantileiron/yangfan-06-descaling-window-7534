"""Initial schema for a fresh Compose volume."""
from sqlalchemy import inspect, text

from src.models.account import Account
from src.models.audit import Event
from src.models.dataset import Dataset
from src.models.model_version import ModelRegistry, ModelVersion
from src.models.review import Review
from src.models.run import Run

SCHEMA = (Account, Dataset, ModelVersion, ModelRegistry, Run, Review, Event)


def migrate(engine):
    tables = [model.__table__ for model in SCHEMA]
    Account.metadata.create_all(engine, tables=tables)
    columns = {column["name"] for column in inspect(engine).get_columns("runs")}
    if "model_version_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE runs ADD COLUMN model_version_id VARCHAR(36) NULL"))
            connection.execute(text("CREATE INDEX ix_runs_model_version_id ON runs (model_version_id)"))
