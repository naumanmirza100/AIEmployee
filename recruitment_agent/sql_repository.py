import json
import os
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
    update,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class SQLRepository:
    """
    Simple SQL Server repository to persist parsed CVs and insights.
    Uses table dbo.ppp_recruitment_agent_cvrecord (aligned with Django CVRecord.db_table).
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.metadata = MetaData(schema="dbo")
        self.cv_records = Table(
            "ppp_recruitment_agent_cvrecord",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("file_name", String(512), nullable=False),
            Column("parsed_json", Text, nullable=False),
            Column("insights_json", Text, nullable=True),
            Column("role_fit_score", Integer, nullable=True),
            Column("rank", Integer, nullable=True),
            Column("enriched_json", Text, nullable=True),
            Column("qualification_json", Text, nullable=True),
            Column("qualification_decision", String(32), nullable=True),
            Column("qualification_confidence", Integer, nullable=True),
            Column("qualification_priority", String(16), nullable=True),
            Column("created_at", DateTime(timezone=True), default=datetime.now(timezone.utc)),
            schema="dbo",
        )
        try:
            # Create table (dbo schema always exists)
            self.metadata.create_all(self.engine, checkfirst=True)
            self._ensure_enriched_column()
            self._ensure_qualification_columns()
        except SQLAlchemyError:
            traceback.print_exc()
            raise

    @classmethod
    def from_env(cls) -> Optional["SQLRepository"]:
        conn = os.environ.get("SQLSERVER_CONN_STRING")
        if not conn:
            return None
        try:
            engine = create_engine(conn, future=True)
            return cls(engine)
        except Exception:
            traceback.print_exc()
            return None
    
    def _ensure_enriched_column(self) -> None:
        try:
            inspector = inspect(self.engine)
            cols = inspector.get_columns("ppp_recruitment_agent_cvrecord", schema="dbo")
            names = {c["name"] for c in cols}
            if "enriched_json" in names:
                return
            with self.engine.begin() as conn:
                conn.execute(text("ALTER TABLE dbo.ppp_recruitment_agent_cvrecord ADD enriched_json NVARCHAR(MAX) NULL"))
        except SQLAlchemyError:
            # Best-effort; ignore if cannot alter (table might not exist yet or column already exists)
            traceback.print_exc()

    def _ensure_qualification_columns(self) -> None:
        try:
            inspector = inspect(self.engine)
            cols = inspector.get_columns("ppp_recruitment_agent_cvrecord", schema="dbo")
            names = {c["name"] for c in cols}
            alter_stmts = []
            if "qualification_json" not in names:
                alter_stmts.append("ALTER TABLE dbo.ppp_recruitment_agent_cvrecord ADD qualification_json NVARCHAR(MAX) NULL")
            if "qualification_decision" not in names:
                alter_stmts.append("ALTER TABLE dbo.ppp_recruitment_agent_cvrecord ADD qualification_decision NVARCHAR(32) NULL")
            if "qualification_confidence" not in names:
                alter_stmts.append("ALTER TABLE dbo.ppp_recruitment_agent_cvrecord ADD qualification_confidence INT NULL")
            if "qualification_priority" not in names:
                alter_stmts.append("ALTER TABLE dbo.ppp_recruitment_agent_cvrecord ADD qualification_priority NVARCHAR(16) NULL")
            for stmt in alter_stmts:
                try:
                    with self.engine.begin() as conn:
                        conn.execute(text(stmt))
                except SQLAlchemyError:
                    # Column might already exist
                    traceback.print_exc()
        except SQLAlchemyError:
            # Table might not exist yet
            traceback.print_exc()

    def store_parsed(self, file_name: str, parsed: Dict[str, Any]) -> Optional[int]:
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    self.cv_records.insert().values(
                        file_name=file_name,
                        parsed_json=json.dumps(parsed, ensure_ascii=False),
                        created_at=datetime.now(timezone.utc),
                    )
                )
                return result.inserted_primary_key[0] if result.inserted_primary_key else None
        except SQLAlchemyError:
            return None

    def store_insights(
        self,
        record_id: Optional[int],
        insights: Dict[str, Any],
        rank: Optional[int] = None,
    ) -> None:
        if record_id is None:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    update(self.cv_records)
                    .where(self.cv_records.c.id == record_id)
                    .values(
                        insights_json=json.dumps(insights, ensure_ascii=False),
                        role_fit_score=insights.get("role_fit_score"),
                        rank=rank,
                    )
                )
        except SQLAlchemyError:
            return

    def store_enrichment(self, record_id: Optional[int], enriched: Dict[str, Any]) -> None:
        if record_id is None:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    update(self.cv_records)
                    .where(self.cv_records.c.id == record_id)
                    .values(enriched_json=json.dumps(enriched, ensure_ascii=False))
                )
        except SQLAlchemyError:
            return

    def store_qualification(
        self,
        record_id: Optional[int],
        qualification: Dict[str, Any],
        rank: Optional[int] = None,
    ) -> None:
        if record_id is None:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    update(self.cv_records)
                    .where(self.cv_records.c.id == record_id)
                    .values(
                        qualification_json=json.dumps(qualification, ensure_ascii=False),
                        qualification_decision=qualification.get("decision"),
                        qualification_confidence=qualification.get("confidence_score"),
                        qualification_priority=qualification.get("priority"),
                        rank=rank if rank is not None else self.cv_records.c.rank,
                    )
                )
        except SQLAlchemyError:
            return

    def fetch_recent(self, limit: int = 20) -> list[Dict[str, Any]]:
        stmt = (
            select(self.cv_records)
            .order_by(self.cv_records.c.created_at.desc())
            .limit(limit)
        )
        with self.engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(row) for row in rows]


