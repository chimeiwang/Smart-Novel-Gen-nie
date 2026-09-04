from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import durable_agent_release_trust as trust_module  # noqa: E402
import github_api_evidence as github_evidence_module  # noqa: E402
from durable_agent_release_broker import (  # noqa: E402
    ORIGINAL_COMMAND,
    BrokerInvalid,
    dispatch_plan,
    policy_sha256,
)
from durable_agent_release_trust import (  # noqa: E402
    ACTIVE_SECRETS,
    BOOTSTRAP_FORMAT,
    EXECUTION_FORCED_COMMAND,
    GITHUB_ARTIFACT_NAMES,
    GITHUB_WORKFLOW_PATHS,
    RETIRED_SECRETS,
    SSH_EVIDENCE_PAYLOAD_FILES,
    SSH_FORMAT,
    UPLOAD_FORCED_COMMAND,
    SshEvidence,
    TrustInvalid,
    build_attestation,
    build_bootstrap_payload,
    build_bootstrap_state,
    build_ssh_payload,
    create_artifact,
    normalize_downloaded_directory,
    validate_bootstrap_transition,
    verify_attestation,
    verify_receipt_chain,
)
from durable_agent_v2_control_bundle import PAYLOAD_FILES  # noqa: E402
from durable_agent_v2_release_receipt import (  # noqa: E402
    FORMAT as RECEIPT_FORMAT,
)
from durable_agent_v2_release_receipt import (  # noqa: E402
    validate as validate_receipt,
)

TRUST_HELPER = SCRIPTS / "durable_agent_release_trust.py"
BROKER_HELPER = SCRIPTS / "durable_agent_release_broker.py"
RECEIPT_HELPER = SCRIPTS / "durable_agent_v2_release_receipt.py"

REPOSITORY = "owner/repo"
ENVIRONMENT = "production"
HOST = "prod.example"
PORT = 22
USER = "deploy"
ISSUED_AT = "2026-09-01T00:00:00Z"
EXPIRES_AT = "2026-09-01T12:00:00Z"
VERIFY_NOW = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
KEY_ID = "release-audit-root-1"


@dataclass(frozen=True)
class Fixture:
    evidence: SshEvidence
    signing_private_key: Path
    trusted_public_key: Path


def _canonical(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _write(path: Path, payload: bytes | str, mode: int = 0o600) -> Path:
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)
    path.chmod(mode)
    return path


def _new_ssh_key(path: Path) -> tuple[Path, Ed25519PrivateKey]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    )
    return _write(path, public + b"\n"), private


def _secret_inventory(path: Path, names: tuple[str, ...]) -> Path:
    return _write(
        path,
        json.dumps(
            {
                "secrets": [{"name": name} for name in names],
                "total_count": len(names),
            },
            separators=(",", ":"),
        ),
    )


def _organization_inventory(
    path: Path,
    names: tuple[str, ...],
    *,
    owner_type: str = "Organization",
) -> Path:
    return _write(
        path,
        _canonical(
            {
                "format": "inkforge-github-organization-secret-inventory/1",
                "owner": {"login": "owner", "type": owner_type},
                "secrets": [{"name": name} for name in names],
                "total_count": len(names),
            }
        ),
    )


def _fixture(tmp_path: Path) -> Fixture:
    host_key, _ = _new_ssh_key(tmp_path / "host.pub")
    execution_key, _ = _new_ssh_key(tmp_path / "execution.pub")
    upload_key, _ = _new_ssh_key(tmp_path / "upload.pub")
    retired_one, _ = _new_ssh_key(tmp_path / "retired-one.pub")
    retired_two, _ = _new_ssh_key(tmp_path / "retired-two.pub")
    host_text = host_key.read_text(encoding="ascii").strip()
    execution_text = execution_key.read_text(encoding="ascii").strip()
    upload_text = upload_key.read_text(encoding="ascii").strip()
    known_hosts = _write(tmp_path / "known_hosts", f"{HOST} {host_text}\n")
    authorized_keys = _write(
        tmp_path / "authorized_keys",
        f'restrict,command="{EXECUTION_FORCED_COMMAND}" {execution_text} execution\n'
        f'restrict,command="{UPLOAD_FORCED_COMMAND}" {upload_text} upload\n',
    )
    environment_secrets = _secret_inventory(
        tmp_path / "environment-secrets.json", tuple(ACTIVE_SECRETS)
    )
    repository_secrets = _secret_inventory(
        tmp_path / "repository-secrets.json", ("UNRELATED_REPOSITORY_SECRET",)
    )
    organization_secrets = _organization_inventory(
        tmp_path / "organization-secrets.json", ("UNRELATED_ORG_SECRET",)
    )
    broker = tmp_path / "broker.py"
    shutil.copy2(BROKER_HELPER, broker)
    broker.chmod(0o755)

    signing = Ed25519PrivateKey.generate()
    private_path = _write(
        tmp_path / "audit-private.pem",
        signing.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    public_path = _write(
        tmp_path / "audit-public.pem",
        signing.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )
    return Fixture(
        evidence=SshEvidence(
            known_hosts=known_hosts,
            host_public_key=host_key,
            authorized_keys=authorized_keys,
            retired_public_keys=(retired_one, retired_two),
            execution_public_key=execution_key,
            upload_public_key=upload_key,
            environment_secrets=environment_secrets,
            repository_secrets=repository_secrets,
            organization_secrets=organization_secrets,
            broker_executable=broker,
        ),
        signing_private_key=private_path,
        trusted_public_key=public_path,
    )


def _ssh_payload(fixture: Fixture) -> dict[str, Any]:
    return build_ssh_payload(
        repository=REPOSITORY,
        environment=ENVIRONMENT,
        host=HOST,
        port=PORT,
        user=USER,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        evidence=fixture.evidence,
    )


def _signed_artifact(
    tmp_path: Path,
    fixture: Fixture,
    *,
    format_name: str = SSH_FORMAT,
    payload: dict[str, Any] | None = None,
    name: str = "attestation",
) -> tuple[Path, str]:
    if payload is None:
        payload = _ssh_payload(fixture)
    document = build_attestation(
        format_name,
        payload,
        signing_private_key=fixture.signing_private_key,
        key_id=KEY_ID,
    )
    directory = tmp_path / name
    digest = create_artifact(directory, document)
    return directory, digest


def _verify_ssh(
    directory: Path,
    digest: str,
    fixture: Fixture,
    *,
    expected_known_hosts_file: Path | None = None,
) -> None:
    verify_attestation(
        directory,
        digest,
        expected_repository=REPOSITORY,
        expected_environment=ENVIRONMENT,
        expected_host=HOST,
        expected_port=PORT,
        expected_user=USER,
        now=VERIFY_NOW,
        ssh_evidence=fixture.evidence,
        trusted_public_key=fixture.trusted_public_key,
        expected_key_id=KEY_ID,
        expected_known_hosts_file=expected_known_hosts_file,
    )


def test_signed_ssh_attestation_is_canonical_and_cross_binds_all_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    directory, digest = _signed_artifact(tmp_path, fixture)

    _verify_ssh(directory, digest, fixture)

    attestation = directory / "ssh-release-attestation.json"
    document = json.loads(attestation.read_text(encoding="utf-8"))
    assert attestation.read_bytes() == _canonical(document)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(attestation.stat().st_mode) == 0o600
    assert document["payload"]["broker"]["policySha256"] == policy_sha256()
    host_key_sha = document["payload"]["server"]["hostPublicKeySha256"]
    assert isinstance(host_key_sha, str) and len(host_key_sha) == 64
    assert document["payload"]["secretPolicy"] == {
        "activeEnvironmentSecrets": list(ACTIVE_SECRETS),
        "retiredSecrets": list(RETIRED_SECRETS),
    }
    keys = document["payload"]["keys"]
    assert keys["executionPublicKeySha256"] != keys["uploadPublicKeySha256"]
    assert keys["executionPublicKeySha256"] not in keys["retiredPublicKeySha256"]
    assert keys["uploadPublicKeySha256"] not in keys["retiredPublicKeySha256"]


def test_known_hosts_secret_is_compared_inside_the_attestation_snapshot(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    directory, digest = _signed_artifact(tmp_path, fixture)
    production_known_hosts = _write(
        tmp_path / "production-known-hosts",
        fixture.evidence.known_hosts.read_bytes(),
    )
    _verify_ssh(
        directory,
        digest,
        fixture,
        expected_known_hosts_file=production_known_hosts,
    )

    _write(production_known_hosts, "attacker.example ssh-ed25519 invalid\n")
    with pytest.raises(TrustInvalid, match="production known_hosts secret"):
        _verify_ssh(
            directory,
            digest,
            fixture,
            expected_known_hosts_file=production_known_hosts,
        )


def test_user_owner_requires_canonical_empty_organization_scope(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    user_inventory = _organization_inventory(
        fixture.evidence.organization_secrets,
        (),
        owner_type="User",
    )
    user_evidence = replace(fixture.evidence, organization_secrets=user_inventory)
    build_ssh_payload(
        repository=REPOSITORY,
        environment=ENVIRONMENT,
        host=HOST,
        port=PORT,
        user=USER,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        evidence=user_evidence,
    )

    _organization_inventory(
        user_inventory,
        ("UNRELATED_ORG_SECRET",),
        owner_type="User",
    )
    with pytest.raises(TrustInvalid, match="必须不存在"):
        build_ssh_payload(
            repository=REPOSITORY,
            environment=ENVIRONMENT,
            host=HOST,
            port=PORT,
            user=USER,
            issued_at=ISSUED_AT,
            expires_at=EXPIRES_AT,
            evidence=user_evidence,
        )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda fixture: _write(
                fixture.evidence.known_hosts,
                fixture.evidence.known_hosts.read_text(encoding="ascii").replace(
                    HOST, "attacker.example"
                ),
            ),
            "known_hosts",
        ),
        (
            lambda fixture: _write(
                fixture.evidence.authorized_keys,
                fixture.evidence.authorized_keys.read_text(encoding="ascii")
                + fixture.evidence.retired_public_keys[0].read_text(encoding="ascii"),
            ),
            "retired",
        ),
        (
            lambda fixture: _write(
                fixture.evidence.authorized_keys,
                fixture.evidence.authorized_keys.read_text(encoding="ascii").replace(
                    "restrict,", "", 1
                ),
            ),
            "execution key",
        ),
        (
            lambda fixture: _secret_inventory(
                fixture.evidence.repository_secrets,
                (ACTIVE_SECRETS[0],),
            ),
            "repository scope",
        ),
        (
            lambda fixture: _organization_inventory(
                fixture.evidence.organization_secrets,
                (RETIRED_SECRETS[0],),
            ),
            "organization scope",
        ),
    ],
)
def test_ssh_attestation_rejects_evidence_swap_or_old_key_residue(
    tmp_path: Path,
    mutator: Callable[[Fixture], object],
    expected: str,
) -> None:
    fixture = _fixture(tmp_path)
    directory, digest = _signed_artifact(tmp_path, fixture)
    mutator(fixture)

    with pytest.raises(TrustInvalid, match=expected):
        _verify_ssh(directory, digest, fixture)


def test_attestation_signature_ttl_canonical_and_subject_attacks_fail(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    directory, _digest = _signed_artifact(tmp_path, fixture)
    path = directory / "ssh-release-attestation.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["server"]["host"] = "attacker.example"
    path.write_bytes(_canonical(document))
    tampered_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "SHA256SUMS").write_text(
        f"{tampered_digest}  ssh-release-attestation.json\n", encoding="ascii"
    )
    with pytest.raises(TrustInvalid, match="签名"):
        _verify_ssh(directory, tampered_digest, fixture)

    expired = _ssh_payload(fixture)
    expired["expiresAt"] = "2026-09-01T00:30:00Z"
    expired_dir, expired_sha = _signed_artifact(tmp_path, fixture, payload=expired, name="expired")
    with pytest.raises(TrustInvalid, match="过期"):
        _verify_ssh(expired_dir, expired_sha, fixture)

    too_long = _ssh_payload(fixture)
    too_long["expiresAt"] = "2026-09-03T00:00:00Z"
    long_dir, long_sha = _signed_artifact(tmp_path, fixture, payload=too_long, name="too-long")
    with pytest.raises(TrustInvalid, match="24 小时"):
        _verify_ssh(long_dir, long_sha, fixture)

    forged_host_subject = _ssh_payload(fixture)
    forged_host_subject["server"]["hostPublicKeySha256"] = "9" * 64
    forged_dir, forged_sha = _signed_artifact(
        tmp_path,
        fixture,
        payload=forged_host_subject,
        name="forged-host-subject",
    )
    with pytest.raises(TrustInvalid, match="server subject"):
        _verify_ssh(forged_dir, forged_sha, fixture)


def test_evidence_reader_rejects_symlink_hardlink_and_read_time_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _write(tmp_path / "target", b"evidence\n")
    symlink = tmp_path / "evidence-link"
    symlink.symlink_to(target)
    with pytest.raises(TrustInvalid, match="安全打开"):
        trust_module._read_regular(symlink, "symlink evidence")  # noqa: SLF001

    hardlinked = tmp_path / "evidence-hardlink"
    os.link(target, hardlinked)
    with pytest.raises(TrustInvalid, match="单链接"):
        trust_module._read_regular(target, "hardlinked evidence")  # noqa: SLF001
    hardlinked.unlink()

    real_fstat = os.fstat
    calls = 0

    def drifting_fstat(descriptor: int) -> os.stat_result | SimpleNamespace:
        nonlocal calls
        current = real_fstat(descriptor)
        calls += 1
        if calls != 2:
            return current
        return SimpleNamespace(
            st_ctime_ns=current.st_ctime_ns,
            st_dev=current.st_dev,
            st_ino=current.st_ino,
            st_mode=current.st_mode,
            st_mtime_ns=current.st_mtime_ns + 1,
            st_nlink=current.st_nlink,
            st_size=current.st_size,
        )

    monkeypatch.setattr(os, "fstat", drifting_fstat)
    with pytest.raises(TrustInvalid, match="读取期间漂移"):
        trust_module._read_regular(target, "drifting evidence")  # noqa: SLF001


def test_github_api_reader_rejects_foreign_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _write(tmp_path / "github-api.json", b"{}\n")
    real_fstat = os.fstat

    def foreign_owner(descriptor: int) -> SimpleNamespace:
        current = real_fstat(descriptor)
        return SimpleNamespace(
            st_ctime_ns=current.st_ctime_ns,
            st_dev=current.st_dev,
            st_gid=current.st_gid,
            st_ino=current.st_ino,
            st_mode=current.st_mode,
            st_mtime_ns=current.st_mtime_ns,
            st_nlink=current.st_nlink,
            st_size=current.st_size,
            st_uid=current.st_uid + 1,
        )

    monkeypatch.setattr(github_evidence_module.os, "fstat", foreign_owner)
    with pytest.raises(TrustInvalid, match="owner 必须是当前 runner"):
        github_evidence_module.read_regular(
            target,
            "GitHub API evidence",
            error_type=TrustInvalid,
        )


def test_github_provenance_requires_exact_external_success_run_and_artifact(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    run_path = _write(
        tmp_path / "run.json",
        json.dumps(
            {
                "conclusion": None,
                "event": "workflow_dispatch",
                "head_branch": "main",
                "head_sha": "a" * 40,
                "id": 123,
                "path": GITHUB_WORKFLOW_PATHS[SSH_FORMAT],
                "repository": {"full_name": REPOSITORY},
                "run_attempt": 1,
                "status": "in_progress",
            },
            separators=(",", ":"),
        ),
    )
    payload = _ssh_payload(fixture)
    document = build_attestation(
        SSH_FORMAT,
        payload,
        github_run_json=run_path,
        artifact_name=GITHUB_ARTIFACT_NAMES[SSH_FORMAT],
    )
    directory = tmp_path / "github-attestation"
    digest = create_artifact(directory, document)
    proof = document["proof"]
    assert "runResponseSha256" not in proof
    assert proof["runIdentity"]["runId"] == "123"
    assert len(proof["runIdentitySha256"]) == 64

    run_document = json.loads(run_path.read_text(encoding="utf-8"))
    run_document["status"] = "completed"
    run_document["conclusion"] = "success"
    _write(run_path, json.dumps(run_document, separators=(",", ":")))
    verify_attestation(
        directory,
        digest,
        expected_repository=REPOSITORY,
        expected_environment=ENVIRONMENT,
        expected_host=HOST,
        expected_port=PORT,
        expected_user=USER,
        now=VERIFY_NOW,
        ssh_evidence=fixture.evidence,
        github_run_json=run_path,
    )

    run_document["conclusion"] = "failure"
    _write(run_path, json.dumps(run_document, separators=(",", ":")))
    with pytest.raises(TrustInvalid, match="provenance"):
        verify_attestation(
            directory,
            digest,
            expected_repository=REPOSITORY,
            expected_environment=ENVIRONMENT,
            expected_host=HOST,
            expected_port=PORT,
            expected_user=USER,
            now=VERIFY_NOW,
            ssh_evidence=fixture.evidence,
            github_run_json=run_path,
        )

    run_document["conclusion"] = "success"
    run_document["run_attempt"] = 2
    _write(run_path, json.dumps(run_document, separators=(",", ":")))
    with pytest.raises(TrustInvalid, match="provenance"):
        verify_attestation(
            directory,
            digest,
            expected_repository=REPOSITORY,
            expected_environment=ENVIRONMENT,
            expected_host=HOST,
            expected_port=PORT,
            expected_user=USER,
            now=VERIFY_NOW,
            ssh_evidence=fixture.evidence,
            github_run_json=run_path,
        )


def _receipt(previous: str | None) -> dict[str, Any]:
    return {
        "activeReleaseCommit": "a" * 40,
        "canaryScopeSha256": "b" * 64,
        "controlBundleSha256": "c" * 64,
        "executionManifestFingerprint": "d" * 64,
        "finalConfig": {
            "routeMode": "off",
            "schemaReady": True,
            "v1FreshStartsEnabled": False,
        },
        "format": RECEIPT_FORMAT,
        "images": {
            "agent": "sha256:" + "1" * 64,
            "core": "sha256:" + "2" * 64,
            "web": "sha256:" + "3" * 64,
        },
        "lock": {
            "action": "route_off_release",
            "lockId": "e" * 64,
            "runAttempt": "1",
            "runId": "123",
        },
        "manifestSha256": "f" * 64,
        "previousReceiptSha256": previous,
        "runtimeIdentity": {
            "boundaryLedgerSha256": "4" * 64,
            "coreContainerId": "container-core",
        },
        "targetReleaseCommit": "a" * 40,
        "workflowTrustedCommit": "a" * 40,
    }


def _write_receipt(root: Path, document: dict[str, Any]) -> str:
    validate_receipt(document, allow_genesis=True)
    payload = _canonical(document)
    digest = hashlib.sha256(payload).hexdigest()
    directory = root / digest
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    _write(directory / "release-receipt.json", payload)
    _write(
        directory / "SHA256SUMS",
        f"{digest}  release-receipt.json\n",
    )
    return digest


def test_bootstrap_attestation_and_state_machine_bind_the_only_null_genesis(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    ssh_dir, ssh_sha = _signed_artifact(tmp_path, fixture, name="ssh")
    _verify_ssh(ssh_dir, ssh_sha, fixture)
    genesis = _receipt(None)
    payload = build_bootstrap_payload(
        repository=REPOSITORY,
        environment=ENVIRONMENT,
        host=HOST,
        port=PORT,
        user=USER,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        ssh_release_attestation_sha256=ssh_sha,
        genesis_receipt=genesis,
    )
    bootstrap_dir, bootstrap_sha = _signed_artifact(
        tmp_path,
        fixture,
        format_name=BOOTSTRAP_FORMAT,
        payload=payload,
        name="bootstrap",
    )
    document, _ = verify_attestation(
        bootstrap_dir,
        bootstrap_sha,
        expected_repository=REPOSITORY,
        expected_environment=ENVIRONMENT,
        expected_host=HOST,
        expected_port=PORT,
        expected_user=USER,
        now=VERIFY_NOW,
        expected_ssh_attestation_sha256=ssh_sha,
        trusted_public_key=fixture.trusted_public_key,
        expected_key_id=KEY_ID,
    )

    prepared = build_bootstrap_state(
        state="prepared",
        attestation_sha256=bootstrap_sha,
        genesis_receipt_sha256=None,
    )
    validate_bootstrap_transition(None, prepared)
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    receipt_root.chmod(0o700)
    genesis_sha = _write_receipt(receipt_root, genesis)
    installed = build_bootstrap_state(
        state="installed",
        attestation_sha256=bootstrap_sha,
        genesis_receipt_sha256=genesis_sha,
    )
    sealed = build_bootstrap_state(
        state="sealed",
        attestation_sha256=bootstrap_sha,
        genesis_receipt_sha256=genesis_sha,
    )
    validate_bootstrap_transition(prepared, installed)
    validate_bootstrap_transition(installed, sealed)
    successor = _receipt(genesis_sha)
    successor["lock"]["lockId"] = "5" * 64
    successor_sha = _write_receipt(receipt_root, successor)
    _write(receipt_root / "current", successor_sha + "\n")

    assert verify_receipt_chain(
        receipt_root=receipt_root,
        bootstrap_payload=document["payload"],
        bootstrap_attestation_sha256=bootstrap_sha,
        sealed_state=sealed,
    ) == [successor_sha, genesis_sha]

    with pytest.raises(TrustInvalid, match="逐步"):
        validate_bootstrap_transition(prepared, sealed)
    changed_attestation = copy.deepcopy(installed)
    changed_attestation["attestationSha256"] = "9" * 64
    with pytest.raises(TrustInvalid, match="更换 attestation"):
        validate_bootstrap_transition(prepared, changed_attestation)


def test_receipt_helper_rejects_untrusted_null_and_chain_rejects_second_genesis(
    tmp_path: Path,
) -> None:
    output = tmp_path / "untrusted-genesis"
    arguments = [
        sys.executable,
        str(RECEIPT_HELPER),
        "create",
        "--output-dir",
        str(output),
        "--active-release-commit",
        "a" * 40,
        "--agent-digest",
        "sha256:" + "1" * 64,
        "--canary-scope-sha256",
        "b" * 64,
        "--control-bundle-sha256",
        "c" * 64,
        "--core-container-id",
        "container-core",
        "--core-digest",
        "sha256:" + "2" * 64,
        "--boundary-ledger-sha256",
        "d" * 64,
        "--execution-manifest-fingerprint",
        "e" * 64,
        "--lock-id",
        "f" * 64,
        "--manifest-sha256",
        "1" * 64,
        "--previous-receipt-sha256",
        "none",
        "--release-action",
        "route_off_release",
        "--route-mode",
        "off",
        "--run-attempt",
        "1",
        "--run-id",
        "123",
        "--schema-ready",
        "true",
        "--target-release-commit",
        "a" * 40,
        "--v1-fresh-starts-enabled",
        "false",
        "--web-digest",
        "sha256:" + "3" * 64,
        "--workflow-trusted-commit",
        "a" * 40,
    ]
    rejected = subprocess.run(  # noqa: S603
        arguments,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "previous=null" in rejected.stderr
    assert not output.exists()

    chain_fixture_dir = tmp_path / "chain-fixture"
    chain_fixture_dir.mkdir()
    fixture = _fixture(chain_fixture_dir)
    ssh_dir, ssh_sha = _signed_artifact(tmp_path, fixture, name="chain-ssh")
    _verify_ssh(ssh_dir, ssh_sha, fixture)
    trusted_genesis = _receipt(None)
    bootstrap_payload = build_bootstrap_payload(
        repository=REPOSITORY,
        environment=ENVIRONMENT,
        host=HOST,
        port=PORT,
        user=USER,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        ssh_release_attestation_sha256=ssh_sha,
        genesis_receipt=trusted_genesis,
    )
    bootstrap_dir, bootstrap_sha = _signed_artifact(
        tmp_path,
        fixture,
        format_name=BOOTSTRAP_FORMAT,
        payload=bootstrap_payload,
        name="chain-bootstrap",
    )
    bootstrap_document, _ = verify_attestation(
        bootstrap_dir,
        bootstrap_sha,
        expected_repository=REPOSITORY,
        expected_environment=ENVIRONMENT,
        expected_host=HOST,
        expected_port=PORT,
        expected_user=USER,
        now=VERIFY_NOW,
        expected_ssh_attestation_sha256=ssh_sha,
        trusted_public_key=fixture.trusted_public_key,
        expected_key_id=KEY_ID,
    )
    receipt_root = tmp_path / "attack-receipts"
    receipt_root.mkdir(mode=0o700)
    receipt_root.chmod(0o700)
    trusted_genesis_sha = _write_receipt(receipt_root, trusted_genesis)
    attacker_genesis = _receipt(None)
    attacker_genesis["activeReleaseCommit"] = "9" * 40
    attacker_genesis["targetReleaseCommit"] = "9" * 40
    attacker_genesis_sha = _write_receipt(receipt_root, attacker_genesis)
    _write(receipt_root / "current", attacker_genesis_sha + "\n")
    sealed = build_bootstrap_state(
        state="sealed",
        attestation_sha256=bootstrap_sha,
        genesis_receipt_sha256=trusted_genesis_sha,
    )
    with pytest.raises(TrustInvalid, match="genesis"):
        verify_receipt_chain(
            receipt_root=receipt_root,
            bootstrap_payload=bootstrap_document["payload"],
            bootstrap_attestation_sha256=bootstrap_sha,
            sealed_state=sealed,
        )

    broken_successor = _receipt("8" * 64)
    broken_successor_sha = _write_receipt(receipt_root, broken_successor)
    _write(receipt_root / "current", broken_successor_sha + "\n")
    with pytest.raises(TrustInvalid, match="链节点"):
        verify_receipt_chain(
            receipt_root=receipt_root,
            bootstrap_payload=bootstrap_document["payload"],
            bootstrap_attestation_sha256=bootstrap_sha,
            sealed_state=sealed,
        )


def _broker_request(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "inkforge-release-broker-request/1",
        "operation": operation,
        "payload": payload,
    }


def _execution_payload() -> dict[str, Any]:
    return {
        "canaryScopeSha256": "1" * 64,
        "controlBundleSha256": "2" * 64,
        "lockId": "3" * 64,
        "manifestSha256": "4" * 64,
        "releaseAction": "route_off_release",
        "routeMode": "off",
        "runAttempt": "1",
        "runId": "123",
        "targetReleaseCommit": "a" * 40,
        "workflowTrustedCommit": "a" * 40,
    }


def test_broker_accepts_only_canonical_fixed_role_operation_and_never_shells(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    _write(request, _canonical(_broker_request("begin_snapshot", _execution_payload())))
    plan = dispatch_plan(
        role="execution",
        original_command=ORIGINAL_COMMAND,
        request_path=request,
    )
    assert plan["program"] == "release-driver"
    assert plan["argv"] == ["begin-snapshot"]
    assert "environment" not in plan and "shell" not in plan

    with pytest.raises(BrokerInvalid, match="SSH_ORIGINAL_COMMAND"):
        dispatch_plan(
            role="execution",
            original_command=f"{ORIGINAL_COMMAND}; id",
            request_path=request,
        )
    with pytest.raises(BrokerInvalid, match="role"):
        dispatch_plan(
            role="upload",
            original_command=ORIGINAL_COMMAND,
            request_path=request,
        )

    extra = _execution_payload()
    extra["argv"] = ["/bin/sh", "-c", "id"]
    _write(request, _canonical(_broker_request("begin_snapshot", extra)))
    with pytest.raises(BrokerInvalid, match="payload 字段"):
        dispatch_plan(
            role="execution",
            original_command=ORIGINAL_COMMAND,
            request_path=request,
        )

    _write(
        request,
        json.dumps(_broker_request("begin_snapshot", _execution_payload()), indent=2) + "\n",
    )
    with pytest.raises(BrokerInvalid, match="canonical"):
        dispatch_plan(
            role="execution",
            original_command=ORIGINAL_COMMAND,
            request_path=request,
        )

    cleanup_payload = _execution_payload()
    cleanup_payload.pop("canaryScopeSha256")
    cleanup_payload.pop("routeMode")
    cleanup_payload["cleanupConfirm"] = "cleanup-failed-release:" + "9" * 64
    _write(
        request,
        _canonical(_broker_request("cleanup_failed_transaction", cleanup_payload)),
    )
    with pytest.raises(BrokerInvalid, match="lock ID"):
        dispatch_plan(
            role="execution",
            original_command=ORIGINAL_COMMAND,
            request_path=request,
        )


def test_download_normalizer_preserves_bytes_and_rejects_extra_or_symlink(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "downloaded-evidence"
    directory.mkdir(mode=0o755)
    before: dict[str, str] = {}
    for name in (*SSH_EVIDENCE_PAYLOAD_FILES, "SHA256SUMS"):
        path = _write(directory / name, f"payload:{name}\n", mode=0o644)
        before[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    normalize_downloaded_directory(directory.resolve(), "ssh-evidence")
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name, digest in before.items():
        path = directory / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest

    extra = directory / "attacker.sh"
    _write(extra, "id\n")
    with pytest.raises(TrustInvalid, match="文件白名单"):
        normalize_downloaded_directory(directory.resolve(), "ssh-evidence")
    extra.unlink()

    target = tmp_path / "outside"
    _write(target, "outside\n", mode=0o644)
    victim = directory / "authorized_keys"
    victim.unlink()
    victim.symlink_to(target)
    with pytest.raises(TrustInvalid, match="安全打开"):
        normalize_downloaded_directory(directory.resolve(), "ssh-evidence")
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_new_trust_is_in_pre_private_key_workflow_but_broker_stays_offline() -> None:
    payload_files = set(PAYLOAD_FILES)
    assert "scripts/durable_agent_release_trust.py" in payload_files
    assert "scripts/durable_agent_release_broker.py" in payload_files
    workflow = (ROOT / ".github/workflows/durable-agent-v2-release.yml").read_text(encoding="utf-8")
    production = workflow.split("  production:", 1)[1]
    assert "durable_agent_release_trust.py verify" in production
    assert production.index("durable_agent_release_trust.py verify") < production.index(
        "streaming-broker-and-sealed-genesis-not-implemented"
    )
    assert "durable_agent_release_broker.py" not in production
    assert "inkforge-release-broker/1" not in workflow


def test_trust_scripts_are_offline_and_parse() -> None:
    for script in (TRUST_HELPER, BROKER_HELPER, RECEIPT_HELPER):
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-c",
                "import ast,pathlib,sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())",
                str(script),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    source = TRUST_HELPER.read_text(encoding="utf-8") + BROKER_HELPER.read_text(encoding="utf-8")
    for forbidden in ("requests.", "urllib.request", "socket.", "subprocess.run", "os.system"):
        assert forbidden not in source
