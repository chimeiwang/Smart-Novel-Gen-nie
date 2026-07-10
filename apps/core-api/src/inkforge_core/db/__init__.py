"""数据库访问基础能力。"""

from .schema_guard import (
    ContractIntegrityError,
    SchemaConnectionError,
    SchemaDiff,
    SchemaVerificationResult,
    add_contract_fingerprint,
    canonical_fingerprint,
    compare_schema_contract,
    export_schema_contract,
    inspect_schema,
    load_schema_contract,
    verify_live_schema,
)

__all__ = [
    "ContractIntegrityError",
    "SchemaConnectionError",
    "SchemaDiff",
    "SchemaVerificationResult",
    "add_contract_fingerprint",
    "canonical_fingerprint",
    "compare_schema_contract",
    "export_schema_contract",
    "inspect_schema",
    "load_schema_contract",
    "verify_live_schema",
]
