from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_explicit_database_export_never_falls_back_to_running_core() -> None:
    source = (ROOT / "scripts/schema_fingerprint.sh").read_text(encoding="utf-8")
    assert '${DATABASE_URL:-}' in source
    assert "SchemaGuardCommand" in source
    assert source.index('${DATABASE_URL:-}') < source.index("docker compose")
    assert "exec java" in source


def test_token_migration_exports_in_separate_limited_java_container() -> None:
    source = (ROOT / ".github/workflows/token-usage-details-migration.yml").read_text(
        encoding="utf-8"
    )
    assert 'docker exec -i "$core_container" /usr/local/bin/inkforge-schema-export' not in source
    assert "docker run --rm -i" in source
    assert '--memory 192m --memory-swap 192m' in source
    assert '--env JAVA_TOOL_OPTIONS=' in source
    assert '--database-url-stdin' in source
    assert '< "$database_url_file"' in source
