from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_api_drift_check_normalizes_line_endings_on_both_sides() -> None:
    source = (ROOT / "scripts" / "generate_api_client.mjs").read_text(encoding="utf-8")

    assert "function normalizeLineEndings" in source
    assert "normalizeLineEndings(current) !== normalizeLineEndings(generated)" in source


def test_generated_client_keeps_numeric_engine_discriminator_literals() -> None:
    generator = (ROOT / "scripts" / "generate_api_client.mjs").read_text(
        encoding="utf-8"
    )
    generated = (
        ROOT / "packages" / "api-client" / "src" / "generated" / "schema.d.ts"
    ).read_text(encoding="utf-8")

    assert "function omitNumericDiscriminators" in generator
    assert "Object.keys(mapping).every((key) => /^\\d+$/.test(key))" in generator
    for schema_name, engine_version in (
        ("WritingRunResponse", 1),
        ("WritingRunStatusResponse", 1),
        ("WritingRunListItem", 1),
        ("CancelWritingRunResponse", 1),
        ("ResumeWritingRunResponse", 1),
        ("WritingRunV2Response", 2),
    ):
        schema_body = generated.split(f"        {schema_name}: {{", 1)[1].split(
            "\n        };", 1
        )[0]
        assert f"engineVersion: {engine_version};" in schema_body
        assert f'engineVersion: "{engine_version}";' not in schema_body
