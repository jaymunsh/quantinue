"""Read-only event-ledger queries used for operational verification."""

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class _IntegerValue(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: int


class _StringValue(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: str


def integer_value(row: object) -> int:
    """Parse one integer SQL projection."""
    return _IntegerValue.model_validate(row).value


def string_value(row: object) -> str:
    """Parse one string SQL projection."""
    return _StringValue.model_validate(row).value


async def count_documents(engine: AsyncEngine, source_name: str) -> int:
    """Count stable provider documents."""
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                """
                SELECT count(*) AS value FROM tb_event_raw_document
                WHERE source_name = :source_name
                """
            ),
            {"source_name": source_name},
        )
        row = result.mappings().one()
    return integer_value(row)


async def latest_raw_text(
    engine: AsyncEngine,
    source_name: str,
    provider_id: str,
) -> str | None:
    """Read the latest immutable raw version."""
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                """
                SELECT version.raw_text AS value
                FROM tb_event_raw_document AS document
                JOIN tb_event_raw_version AS version USING (document_id)
                WHERE document.source_name = :source_name
                  AND document.source_document_id = :provider_id
                ORDER BY version.version_no DESC
                LIMIT 1
                """
            ),
            {"source_name": source_name, "provider_id": provider_id},
        )
        row = result.mappings().one_or_none()
    return None if row is None else string_value(row)
