#!/bin/sh
set -eu
umask 077
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

action="${1:-}"
argument="${2:-}"
[ "$#" -le 2 ] || { echo "durable-release:error:参数过多" >&2; exit 2; }
case "$action" in
  source-guard|target-snapshot|begin-snapshot|begin-rollback|create-manifest|verify-manifest|runtime-preflight|verify-drain-binding|transition-runtime-config|prepare-release|consume-live-boundary|mark-live-boundary-applied|boundary-ledger|release-database|allowlist-gate|rollback-preflight|rollback-postflight|transaction-postflight|finalize-allowlist-transaction|transaction-status|reconcile-transaction|commit-transaction|mark-transaction-failed|cleanup-failed-transaction) ;;
  *) echo "durable-release:error:动作无效" >&2; exit 2 ;;
esac

app_dir="${APP_DIR:-$(pwd)}"
control_dir="${DURABLE_AGENT_CONTROL_BUNDLE_DIR:-$app_dir}"
control_bundle_sha="${DURABLE_AGENT_CONTROL_BUNDLE_SHA256:-}"
manifest_helper="$control_dir/scripts/durable_agent_v2_release_manifest.py"
receipt_helper="$control_dir/scripts/durable_agent_v2_release_receipt.py"
development_evidence_helper="$control_dir/scripts/durable_agent_v2_development_evidence.py"
image_verifier="$control_dir/scripts/verify-durable-agent-v2-image.sh"
rollout_gate="$control_dir/scripts/durable-agent-v2-rollout-gate.sh"
migration_helper="$control_dir/scripts/durable-agent-execution-migration.sh"
joint_drain_helper="$control_dir/scripts/durable_agent_joint_drain.py"
boundary_helper="$control_dir/scripts/durable_agent_release_boundary.py"
guard_helper="$control_dir/scripts/durable_agent_release_guard.py"
guard_compose_file="$control_dir/infra/compose.durable-agent-release-guard.yaml"
control_bundle_verifier="$control_dir/scripts/durable_agent_v2_control_bundle.py"
workflow_commit="${WORKFLOW_TRUSTED_COMMIT:-}"
target_commit="${TARGET_RELEASE_COMMIT:-$workflow_commit}"
release_lock_id="${DURABLE_AGENT_RELEASE_LOCK_ID:-}"
release_lock_file="$app_dir/.durable-agent-v2-release-transaction.lock"
release_lock_state_root="$app_dir/.durable-agent-v2-release-transactions"
release_lock_dir="$release_lock_state_root/$release_lock_id"
release_lock_owner="$release_lock_dir/owner"
release_lock_state="$release_lock_dir/state"
release_lock_partial_owner="$app_dir/.durable-agent-v2-release-owner.$release_lock_id.partial"
release_receipt_root="$app_dir/.durable-agent-v2-release-receipts"
boundary_evidence_dir="$release_lock_dir/boundary-evidence"
release_guard_root="$app_dir/.durable-agent-v2-release-guard"
release_guard_file="$release_guard_root/guard.json"

require_nonempty() {
  [ -n "$1" ] || {
    echo "durable-release:error:$2" >&2
    exit 1
  }
}

require_commit() {
  value="$1"
  label="$2"
  case "$value" in
    ""|*[!0-9a-f]*) echo "durable-release:error:$label" >&2; exit 1 ;;
  esac
  [ "${#value}" -eq 40 ] || {
    echo "durable-release:error:$label" >&2
    exit 1
  }
}

require_github_dispatch() {
  require_commit "$workflow_commit" workflow-trusted-commit
  [ "${GITHUB_ACTIONS:-}" = "true" ] \
    && [ "${GITHUB_EVENT_NAME:-}" = "workflow_dispatch" ] \
    && [ "${GITHUB_REF:-}" = "refs/heads/main" ] \
    && [ "${GITHUB_SHA:-}" = "$workflow_commit" ] || {
      echo "durable-release:error:github-main-dispatch" >&2
      exit 1
    }
}

require_production_approval() {
  require_github_dispatch
  [ "${INKFORGE_RELEASE_APPROVED_ENVIRONMENT:-}" = "production" ] || {
    echo "durable-release:error:production-approval" >&2
    exit 1
  }
}

require_control_bundle() {
  require_sha256 "$control_bundle_sha" control-bundle-sha256
  [ "$control_dir" != "$app_dir" ] || {
    echo "durable-release:error:control-bundle-must-not-be-app-dir" >&2
    exit 1
  }
  [ -d "$control_dir" ] && [ ! -L "$control_dir" ] \
    && [ -r "$control_bundle_verifier" ] || {
      echo "durable-release:error:control-bundle-missing" >&2
      exit 1
    }
  output="$(python3 "$control_bundle_verifier" verify \
    --bundle-dir "$control_dir" --expected-sha256 "$control_bundle_sha")" || {
      echo "durable-release:error:control-bundle-invalid" >&2
      exit 1
    }
  [ "$output" = "control-bundle-verified:$control_bundle_sha" ] || {
    echo "durable-release:error:control-bundle-output" >&2
    exit 1
  }
  python3 - "$control_dir/control-bundle.json" "$workflow_commit" \
    "$target_commit" "${GITHUB_RUN_ID:-}" "${GITHUB_RUN_ATTEMPT:-}" <<'PY'
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "workflowTrustedCommit": sys.argv[2],
    "targetReleaseCommit": sys.argv[3],
    "producerRunId": sys.argv[4],
    "producerRunAttempt": sys.argv[5],
}
if any(document.get(key) != value for key, value in expected.items()):
    raise SystemExit("control-bundle-provenance")
PY
}

require_source_guard() {
  require_github_dispatch
  command -v git >/dev/null 2>&1 || {
    echo "durable-release:error:missing-git" >&2
    exit 1
  }
  require_commit "$target_commit" target-release-commit
  [ "$target_commit" = "$workflow_commit" ] || {
    echo "durable-release:error:source-target-commit" >&2
    exit 1
  }
  [ "${CLI_COMMIT:-$target_commit}" = "$target_commit" ] || {
    echo "durable-release:error:cli-commit" >&2
    exit 1
  }
  head_commit="$(git -C "$app_dir" rev-parse HEAD)" || {
    echo "durable-release:error:git-head" >&2
    exit 1
  }
  main_commit="$(git -C "$app_dir" rev-parse refs/remotes/origin/main)" || {
    echo "durable-release:error:git-main" >&2
    exit 1
  }
  [ "$head_commit" = "$workflow_commit" ] \
    && [ "$main_commit" = "$workflow_commit" ] || {
    echo "durable-release:error:immutable-main-commit" >&2
    exit 1
  }
}

require_release_files() {
  [ -r "$image_verifier" ] || {
    echo "durable-release:error:missing-image-verifier" >&2
    exit 1
  }
}

require_manifest_helper() {
  [ -r "$manifest_helper" ] || {
    echo "durable-release:error:missing-manifest-helper" >&2
    exit 1
  }
}

require_image_verifier() {
  [ -r "$image_verifier" ] || {
    echo "durable-release:error:missing-image-verifier" >&2
    exit 1
  }
}

validate_digest() {
  digest="$1"
  case "$digest" in
    sha256:*) digest_hex="${digest#sha256:}" ;;
    *) return 1 ;;
  esac
  case "$digest_hex" in ""|*[!0-9a-f]*) return 1 ;; esac
  [ "${#digest_hex}" -eq 64 ]
}

canonical_image_id() {
  image="$1"
  actual="$(docker image inspect --format '{{.Id}}' "$image")" || {
    echo "durable-release:error:image-missing" >&2
    exit 1
  }
  validate_digest "$actual" || {
    echo "durable-release:error:image-digest" >&2
    exit 1
  }
  printf '%s\n' "$actual"
}

require_exact_image() {
  image="$1"
  expected="$2"
  validate_digest "$expected" || {
    echo "durable-release:error:expected-image-digest" >&2
    exit 1
  }
  actual="$(canonical_image_id "$image")"
  [ "$actual" = "$expected" ] || {
    echo "durable-release:error:image-digest-drift" >&2
    exit 1
  }
}

parse_agent_probe() {
  probe="$1"
  case "$probe" in
    v2-aware-image-ok:agent:*) fingerprint="${probe#v2-aware-image-ok:agent:}" ;;
    *) echo "durable-release:error:agent-probe-output" >&2; exit 1 ;;
  esac
  case "$fingerprint" in ""|*[!0-9a-f]*) exit 1 ;; esac
  [ "${#fingerprint}" -eq 64 ] || exit 1
  printf '%s\n' "$fingerprint"
}

current_service_digest() (
  service="$1"
  repository="$2"
  containers="$(docker ps -q \
    --filter label=com.docker.compose.project=inkforge \
    --filter "label=com.docker.compose.service=$service")" || {
      echo "durable-release:error:runtime-container-query" >&2
      exit 1
    }
  # shellcheck disable=SC2086
  set -- $containers
  [ "$#" -eq 1 ] || {
    echo "durable-release:error:runtime-container-count" >&2
    exit 1
  }
  container="$1"
  declared="$(docker inspect --format '{{.Config.Image}}' "$container")" || exit 1
  case "$declared" in
    "$repository":*) ;;
    *) echo "durable-release:error:runtime-image-repository" >&2; exit 1 ;;
  esac
  digest="$(docker inspect --format '{{.Image}}' "$container")" || exit 1
  validate_digest "$digest" || {
    echo "durable-release:error:runtime-image-digest" >&2
    exit 1
  }
  canonical="$(canonical_image_id "$digest")"
  [ "$canonical" = "$digest" ] || {
    echo "durable-release:error:runtime-image-drift" >&2
    exit 1
  }
  printf '%s\n' "$digest"
)

manifest_read() (
  field="$1"
  manifest_directory="${RELEASE_MANIFEST_DIR:-}"
  manifest_expected_sha="${RELEASE_MANIFEST_SHA256:-}"
  require_nonempty "$manifest_directory" release-manifest-dir
  require_nonempty "$manifest_expected_sha" release-manifest-sha256
  python3 - "$manifest_directory" "$manifest_expected_sha" \
    "$target_commit" "$field" <<'PY'
import hashlib
import json
import stat
import sys
from pathlib import Path

directory = Path(sys.argv[1])
expected_sha, expected_target, field = sys.argv[2:]
paths = {
    "canary-scope-sha256": ("canaryScopeSha256",),
    "development-evidence-sha256": ("developmentEvidenceSha256",),
    "control-bundle-sha256": ("controlBundleSha256",),
    "workflow-trusted-commit": ("workflowTrustedCommit",),
    "target-release-commit": ("targetReleaseCommit",),
    "rollback-source-release-commit": ("rollbackSourceReleaseCommit",),
    "rollback-source-receipt-sha256": ("rollbackSourceReceiptSha256",),
    "route-mode": ("routeMode",),
    "source-manifest-fingerprint": ("executionManifestFingerprints", "source"),
    "target-manifest-fingerprint": ("executionManifestFingerprints", "target"),
    "rollback-manifest-fingerprint": ("executionManifestFingerprints", "rollback"),
    "target-web-digest": ("images", "target", "web"),
    "target-core-digest": ("images", "target", "core"),
    "target-agent-digest": ("images", "target", "agent"),
    "rollback-web-digest": ("images", "rollback", "web"),
    "rollback-core-digest": ("images", "rollback", "core"),
    "rollback-agent-digest": ("images", "rollback", "agent"),
}
if field not in paths or directory.is_symlink() or not directory.is_dir():
    raise SystemExit("manifest-path")
manifest = directory / "release-manifest.json"
checksums = directory / "SHA256SUMS"
if {path.name for path in directory.iterdir()} != {manifest.name, checksums.name}:
    raise SystemExit("manifest-files")
for path in (manifest, checksums):
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SystemExit("manifest-file")

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result

payload = manifest.read_bytes()
actual_sha = hashlib.sha256(payload).hexdigest()
if actual_sha != expected_sha or checksums.read_text(encoding="ascii") != (
    f"{actual_sha}  release-manifest.json\n"
):
    raise SystemExit("manifest-sha")
document = json.loads(payload.decode("utf-8"), object_pairs_hook=unique)
canonical = (
    json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n"
).encode()
if payload != canonical or document.get("format") != "inkforge-durable-agent-v2-release/3":
    raise SystemExit("manifest-canonical")
if document.get("targetReleaseCommit") != expected_target:
    raise SystemExit("manifest-target")
value = document
for key in paths[field]:
    value = value[key]
if not isinstance(value, str):
    raise SystemExit("manifest-field")
print(value)
PY
)

verify_manifest() (
  manifest_read target-release-commit >/dev/null
  manifest_read source-manifest-fingerprint >/dev/null
  if [ "${RELEASE_ACTION:-}" != rollback ]; then
    [ "$(manifest_read control-bundle-sha256)" = "$control_bundle_sha" ] || {
      echo "durable-release:error:manifest-control-bundle" >&2
      exit 1
    }
  fi
)

snapshot_value() {
  snapshot_path="$1"
  snapshot_kind="$2"
  snapshot_key="$3"
  python3 - "$snapshot_path" "$snapshot_kind" "$snapshot_key" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
kind = sys.argv[2]
requested = sys.argv[3]
expected = {
    "target": {
        "targetWebDigest",
        "targetCoreDigest",
        "targetAgentDigest",
        "targetManifestFingerprint",
    },
    "rollback": {
        "rollbackWebDigest",
        "rollbackCoreDigest",
        "rollbackAgentDigest",
        "rollbackManifestFingerprint",
        "rollbackSourceReleaseCommit",
        "rollbackSourceReceiptSha256",
        "runtimeRoute",
        "runtimeSchemaReady",
        "runtimeV1FreshStartsEnabled",
        "runtimeCanaryScopeSha256",
    },
}[kind]
values: dict[str, str] = {}
for raw_line in path.read_text(encoding="ascii").splitlines():
    if raw_line.count("=") != 1:
        raise SystemExit("snapshot-format")
    key, value = raw_line.split("=", 1)
    if key not in expected or key in values or not value:
        raise SystemExit("snapshot-format")
    values[key] = value
if set(values) != expected or requested not in values:
    raise SystemExit("snapshot-format")
print(values[requested])
PY
}

runtime_preflight() (
  group="$1"
  case "$group" in target|rollback) ;; *) exit 2 ;; esac
  require_release_files
  verify_manifest
  require_release_lock
  web_expected="$(manifest_read "$group-web-digest")"
  core_expected="$(manifest_read "$group-core-digest")"
  agent_expected="$(manifest_read "$group-agent-digest")"
  manifest_expected="$(manifest_read "$group-manifest-fingerprint")"
  web_actual="$(current_service_digest web inkforge-web)"
  core_actual="$(current_service_digest core-api inkforge-core-api)"
  agent_actual="$(current_service_digest agent-service inkforge-agent-service)"
  [ "$web_actual" = "$web_expected" ] \
    && [ "$core_actual" = "$core_expected" ] \
    && [ "$agent_actual" = "$agent_expected" ] || {
      echo "durable-release:error:runtime-digest-drift" >&2
      exit 1
    }
  sh "$image_verifier" core "$core_actual" >/dev/null
  agent_probe="$(sh "$image_verifier" agent "$agent_actual" "$manifest_expected")" || {
    echo "durable-release:error:runtime-agent-incompatible" >&2
    exit 1
  }
  parse_agent_probe "$agent_probe" >/dev/null
  expected_route="${EXPECTED_RUNTIME_ROUTE_MODE:-$(manifest_read route-mode)}"
  expected_scope="$(manifest_read canary-scope-sha256)"
  current_core_config_snapshot "$expected_route" "$expected_scope" >/dev/null
)

require_route_mode() {
  expected="$1"
  actual="$(manifest_read route-mode)"
  [ "$actual" = "$expected" ] || {
    echo "durable-release:error:manifest-route-mode" >&2
    exit 1
  }
}

run_migration_helper() {
  APP_DIR="$control_dir" \
  DURABLE_AGENT_MIGRATION_ENV_FILE="$app_dir/.env" \
  DURABLE_AGENT_MIGRATION_BACKUP_ROOT="$app_dir/.durable-agent-execution-backups/${2:-novelwriter}" \
    sh "$migration_helper" "$@"
}

run_rollout_gate() {
  APP_DIR="$control_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$app_dir/.env" \
    sh "$rollout_gate" "$@"
}

route_off_gate_for_current_state() (
  allow_initialize="$1"
  config="$(python3 - "$app_dir/.env" <<'PY'
import sys
from pathlib import Path

allowed = {
    "DURABLE_AGENT_EXECUTION_SCHEMA_READY",
    "DURABLE_AGENT_EXECUTION_ROUTE_MODE",
    "V1_FRESH_AGENT_STARTS_ENABLED",
}
values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key not in allowed:
        continue
    if key in values:
        raise SystemExit("route-off-config-duplicate")
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    values[key] = value.lower()
schema_ready = values.get("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "false")
route = values.get("DURABLE_AGENT_EXECUTION_ROUTE_MODE", "off")
v1_fresh = values.get("V1_FRESH_AGENT_STARTS_ENABLED", "true")
if schema_ready not in {"true", "false"} or route != "off" or v1_fresh not in {
    "true",
    "false",
}:
    raise SystemExit("route-off-config-invalid")
print(f"{schema_ready}:{route}:{v1_fresh}")
PY
)" || {
    echo "durable-release:error:route-off-config" >&2
    exit 1
  }
  state="$(run_migration_helper status novelwriter)" || exit 1
  case "$state:$config" in
    migrated-empty-v2:false:off:false)
      run_rollout_gate post-contract-route-off novelwriter
      [ "$allow_initialize" = true ] || return 0
      transition_runtime_config schema-ready-off >/dev/null
      run_rollout_gate schema-ready-route-off novelwriter
      run_rollout_gate initialize-drain-indexes novelwriter
      run_rollout_gate route-off-drain novelwriter
      ;;
    migrated-empty-v2:true:off:false)
      if [ "$allow_initialize" = true ]; then
        run_rollout_gate initialize-drain-indexes novelwriter
      fi
      run_rollout_gate route-off-drain novelwriter
      ;;
    migrated-with-v2:true:off:false)
      run_rollout_gate route-off-drain novelwriter
      ;;
    *)
      echo "durable-release:error:route-off-stage" >&2
      exit 1
      ;;
  esac
)

require_sha256() {
  value="$1"
  label="$2"
  case "$value" in ""|*[!0-9a-f]*) echo "durable-release:error:$label" >&2; exit 1 ;; esac
  [ "${#value}" -eq 64 ] || {
    echo "durable-release:error:$label" >&2
    exit 1
  }
}

require_positive_decimal() {
  value="$1"
  label="$2"
  case "$value" in ""|0|*[!0-9]*) echo "durable-release:error:$label" >&2; exit 1 ;; esac
}

private_mode() {
  python3 - "$1" <<'PY'
import stat
import sys
from pathlib import Path

print(f"{stat.S_IMODE(Path(sys.argv[1]).stat().st_mode):o}")
PY
}

validate_release_action() {
  case "$1" in route_off_release|allowlist_release|rollback) ;;
    *) echo "durable-release:error:release-action" >&2; exit 1 ;;
  esac
}

write_lock_owner_file() {
  path="$1"
  owner_run_id="${2:-$GITHUB_RUN_ID}"
  owner_run_attempt="${3:-$GITHUB_RUN_ATTEMPT}"
  owner_operation="${4:-$RELEASE_ACTION}"
  owner_workflow_commit="${5:-$workflow_commit}"
  owner_target_commit="${6:-$target_commit}"
  python3 - "$path" "$release_lock_id" "$owner_run_id" "$owner_run_attempt" \
    "$owner_operation" "$owner_workflow_commit" "$owner_target_commit" \
    "$control_bundle_sha" <<'PY'
import os
import sys

path = sys.argv[1]
values = (
    ("format", "2"),
    ("lockId", sys.argv[2]),
    ("runId", sys.argv[3]),
    ("runAttempt", sys.argv[4]),
    ("operation", sys.argv[5]),
    ("workflowTrustedCommit", sys.argv[6]),
    ("targetReleaseCommit", sys.argv[7]),
    ("controlBundleSha256", sys.argv[8]),
)
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as target:
    for key, value in values:
        target.write(f"{key}={value}\n")
    target.flush()
    os.fsync(target.fileno())
PY
}

write_lock_state() {
  wanted="$1"
  case "$wanted" in active|prepared|committed_cleanup_pending|failed) ;;
    *) exit 2 ;;
  esac
  python3 - "$release_lock_dir" "$release_lock_owner" "$release_lock_file" \
    "$release_lock_state" "$wanted" \
    "${DURABLE_AGENT_RELEASE_FAULT_POINT:-}" \
    "${INKFORGE_LOCAL_RELEASE_TEST_MODE:-}" <<'PY'
import hashlib
import os
import re
import stat
import sys
from pathlib import Path

directory, owner, fixed, state_path = map(Path, sys.argv[1:5])
wanted, fault_point, test_mode = sys.argv[5:8]
states = {"active", "prepared", "committed_cleanup_pending", "failed"}
partial_pattern = re.compile(
    r"\.state-([0-9a-f]{64})-(active|prepared|committed_cleanup_pending|failed)\.partial\Z"
)


def fail(code: str) -> None:
    print(f"durable-release:error:{code}", file=sys.stderr)
    raise SystemExit(1)


def fault(point: str) -> None:
    if fault_point != point:
        return
    if test_mode != "true":
        fail("production-fault-injection-disabled")
    print(f"durable-release:test-fault:{point}", file=sys.stderr)
    raise SystemExit(90)


def private_regular(path: Path, mode: int) -> bool:
    return (
        path.exists()
        and not path.is_symlink()
        and path.is_file()
        and stat.S_IMODE(path.stat().st_mode) == mode
    )


if wanted not in states:
    fail("lock-state-target")
if (
    not directory.exists()
    or directory.is_symlink()
    or not directory.is_dir()
    or stat.S_IMODE(directory.stat().st_mode) != 0o700
):
    fail("lock-state-directory")
if not private_regular(owner, 0o600) or not private_regular(fixed, 0o600):
    fail("lock-state-owner")
try:
    if not owner.samefile(fixed):
        fail("lock-state-owner-inode")
except OSError:
    fail("lock-state-owner-inode")

owner_sha = hashlib.sha256(owner.read_bytes()).hexdigest()
expected_name = f".state-{owner_sha}-{wanted}.partial"
state_partials = [
    path
    for path in directory.iterdir()
    if path.name.startswith(".state") and path.name.endswith(".partial")
]
if len(state_partials) > 1:
    fail("lock-state-multiple-partials")
partial: Path | None = state_partials[0] if state_partials else None
if partial is not None:
    match = partial_pattern.fullmatch(partial.name)
    if (
        match is None
        or partial.name != expected_name
        or match.group(1) != owner_sha
        or match.group(2) != wanted
    ):
        fail("lock-state-foreign-partial")
    if not private_regular(partial, 0o600):
        fail("lock-state-partial")
    if partial.read_bytes() != f"{wanted}\n".encode("ascii"):
        fail("lock-state-partial-content")

if state_path.exists() or state_path.is_symlink():
    if not private_regular(state_path, 0o600):
        fail("lock-state-file")
    current = state_path.read_text(encoding="ascii")
    if current not in {f"{value}\n" for value in states}:
        fail("lock-state-content")
    if current == f"{wanted}\n":
        if partial is not None:
            fail("lock-state-ambiguous-partial")
        descriptor = os.open(state_path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        parent = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        raise SystemExit(0)
elif wanted != "active":
    fail("lock-state-missing")

if partial is None:
    partial = directory / expected_name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(partial, flags, 0o600)
    except OSError:
        fail("lock-state-partial-create")
    with os.fdopen(descriptor, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(f"{wanted}\n".encode("ascii"))
        output.flush()
        os.fsync(output.fileno())
else:
    descriptor = os.open(partial, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

fault("state-after-partial-fsync")
os.replace(partial, state_path)
fault("state-after-replace")
parent = os.open(directory, os.O_RDONLY)
try:
    os.fsync(parent)
finally:
    os.close(parent)
PY
}

write_private_line_no_replace() {
  path="$1"
  value="$2"
  python3 - "$path" "$value" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as output:
    output.write(sys.argv[2] + "\n")
    output.flush()
    os.fsync(output.fileno())
directory = os.open(path.parent, os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
}

verify_env_snapshot() {
  snapshot="$1"
  checksum_file="$snapshot.sha256"
  [ -f "$snapshot" ] && [ ! -L "$snapshot" ] \
    && [ "$(private_mode "$snapshot")" = 600 ] \
    && [ -f "$checksum_file" ] && [ ! -L "$checksum_file" ] \
    && [ "$(private_mode "$checksum_file")" = 600 ] || return 1
  expected="$(sed -n '1p' "$checksum_file")"
  [ "$(wc -l < "$checksum_file" | tr -d ' ')" = 1 ] || return 1
  require_sha256 "$expected" env-snapshot-sha256
  [ "$(sha256sum "$snapshot" | cut -d ' ' -f 1)" = "$expected" ]
}

begin_release_lock() {
  require_production_approval
  require_sha256 "$release_lock_id" release-lock-id
  require_positive_decimal "${GITHUB_RUN_ID:-}" github-run-id
  require_positive_decimal "${GITHUB_RUN_ATTEMPT:-}" github-run-attempt
  RELEASE_ACTION="${RELEASE_ACTION:-}"
  require_nonempty "$RELEASE_ACTION" release-action
  validate_release_action "$RELEASE_ACTION"
  require_commit "$target_commit" target-release-commit
  require_control_bundle
  [ -d "$app_dir" ] && [ ! -L "$app_dir" ] || {
    echo "durable-release:error:app-dir" >&2
    exit 1
  }
  mkdir -p "$release_lock_state_root"
  chmod 700 "$release_lock_state_root"
  [ ! -e "$release_lock_partial_owner" ] || {
    echo "durable-release:error:lock-owner-partial" >&2
    exit 1
  }
  write_lock_owner_file "$release_lock_partial_owner"
  if ! ln "$release_lock_partial_owner" "$release_lock_file" 2>/dev/null; then
    rm -f -- "$release_lock_partial_owner"
    echo "durable-release:error:release-transaction-locked" >&2
    exit 1
  fi
  mkdir "$release_lock_dir" 2>/dev/null || {
    echo "durable-release:error:release-transaction-state-dir" >&2
    exit 1
  }
  chmod 700 "$release_lock_dir"
  mv "$release_lock_partial_owner" "$release_lock_owner"
  write_lock_state active
}

verify_lock_owner() {
  owner_path="$1"
  expected_run_id="$2"
  expected_run_attempt="$3"
  expected_operation="$4"
  expected_workflow_commit="${5:-$workflow_commit}"
  expected_target_commit="${6:-$target_commit}"
  expected_control_sha="${7:-$control_bundle_sha}"
  python3 - "$owner_path" "$release_lock_id" "$expected_run_id" \
    "$expected_run_attempt" "$expected_operation" "$expected_workflow_commit" \
    "$expected_target_commit" "$expected_control_sha" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.is_symlink() or not path.is_file():
    raise SystemExit("lock-owner-file")
if stat.S_IMODE(path.stat().st_mode) & 0o077:
    raise SystemExit("lock-owner-mode")
expected = {
    "format": "2",
    "lockId": sys.argv[2],
    "runId": sys.argv[3],
    "runAttempt": sys.argv[4],
    "operation": sys.argv[5],
    "workflowTrustedCommit": sys.argv[6],
    "targetReleaseCommit": sys.argv[7],
    "controlBundleSha256": sys.argv[8],
}
actual = {}
for raw in path.read_text(encoding="ascii").splitlines():
    if raw.count("=") != 1:
        raise SystemExit("lock-owner-format")
    key, value = raw.split("=", 1)
    if key in actual:
        raise SystemExit("lock-owner-duplicate")
    actual[key] = value
if actual != expected:
    raise SystemExit("lock-owner-mismatch")
PY
}

require_release_lock_identity() {
  require_production_approval
  require_sha256 "$release_lock_id" release-lock-id
  require_positive_decimal "${GITHUB_RUN_ID:-}" github-run-id
  require_positive_decimal "${GITHUB_RUN_ATTEMPT:-}" github-run-attempt
  RELEASE_ACTION="${RELEASE_ACTION:-}"
  require_nonempty "$RELEASE_ACTION" release-action
  validate_release_action "$RELEASE_ACTION"
  require_control_bundle
  [ -f "$release_lock_file" ] && [ ! -L "$release_lock_file" ] \
    && [ -d "$release_lock_dir" ] && [ ! -L "$release_lock_dir" ] || {
    echo "durable-release:error:release-transaction-lock-missing" >&2
    exit 1
  }
  [ "$(private_mode "$release_lock_dir")" = 700 ] || {
    echo "durable-release:error:release-transaction-lock-mode" >&2
    exit 1
  }
  [ "$(private_mode "$release_lock_file")" = 600 ] \
    && [ "$(private_mode "$release_lock_state")" = 600 ] || {
      echo "durable-release:error:release-transaction-lock-mode" >&2
      exit 1
    }
  verify_lock_owner "$release_lock_file" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" \
    "$RELEASE_ACTION" || {
      echo "durable-release:error:release-transaction-owner" >&2
      exit 1
    }
  verify_lock_owner "$release_lock_owner" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" \
    "$RELEASE_ACTION" || exit 1
  [ "$release_lock_file" -ef "$release_lock_owner" ] || {
    echo "durable-release:error:release-transaction-owner-inode" >&2
    exit 1
  }
}

require_release_lock() {
  require_release_lock_identity
  case "$(cat "$release_lock_state")" in
    active|prepared|committed_cleanup_pending) ;;
    *)
      echo "durable-release:error:release-transaction-lock-state" >&2
      exit 1
      ;;
  esac
}

require_failed_release_lock() {
  require_release_lock_identity
  [ "$(cat "$release_lock_state")" = failed ] || {
    echo "durable-release:error:release-transaction-lock-state" >&2
    exit 1
  }
}

mark_lock_failed() {
  require_release_lock
  write_lock_state failed
}

mark_settled_compensation_failed() (
  case "$RELEASE_ACTION" in
    rollback) expected_boundary=compose-rollback ;;
    route_off_release|allowlist_release) expected_boundary=compose-release ;;
    *) return 1 ;;
  esac
  base_file="$release_lock_dir/base-receipt.sha256"
  [ -f "$base_file" ] && [ ! -L "$base_file" ] || return 2
  require_sha256 "$(cat "$base_file")" base-receipt-sha256
  for receipt_path in \
    "$release_lock_dir/expected-receipt.sha256" \
    "$release_lock_dir/receipt-intent.json" \
    "$release_lock_dir/release-receipt-candidate" \
    "$release_lock_dir/receipt-current-unfsynced" \
    "$release_lock_dir/receipt-commit-confirmed"
  do
    [ ! -e "$receipt_path" ] && [ ! -L "$receipt_path" ] || return 2
  done
  [ -d "$boundary_evidence_dir" ] && [ ! -L "$boundary_evidence_dir" ] \
    || return 2
  # shellcheck disable=SC2086
  set -- "$boundary_evidence_dir/"[0-9][0-9][0-9][0-9][0-9][0-9]-"$expected_boundary".applied.json
  [ "$#" -eq 1 ] && [ -f "$1" ] && [ ! -L "$1" ] || {
    [ ! -e "$1" ] && return 2
    return 1
  }
  ledger="$(python3 "$boundary_helper" ledger \
    --evidence-dir "$boundary_evidence_dir" \
    --lock-id "$release_lock_id" 2>/dev/null)" || return 1
  validation_status=0
  python3 - "$ledger" "$release_lock_id" "$expected_boundary" <<'PY' \
    || validation_status=$?
import json
import sys

document = json.loads(sys.argv[1])
if set(document) != {"entries", "format", "lockId"}:
    raise SystemExit(1)
if (
    document["format"] != "inkforge-durable-agent-v2-boundary-ledger/1"
    or document["lockId"] != sys.argv[2]
    or not isinstance(document["entries"], list)
    or not document["entries"]
):
    raise SystemExit(1)
entries = document["entries"]
matches = [entry for entry in entries if entry.get("boundary") == sys.argv[3]]
if len(matches) != 1:
    raise SystemExit(1)
entry = matches[0]
if entry.get("outcome") == "succeeded":
    raise SystemExit(2)
if entry.get("outcome") != "compensated" or entry is not entries[-1]:
    raise SystemExit(1)
PY
  case "$validation_status" in
    0) ;;
    2) return 2 ;;
    *) return 1 ;;
  esac
  runtime_group="$(boundary_runtime_group "$expected_boundary")"
  EXPECTED_RUNTIME_ROUTE_MODE=off runtime_preflight "$runtime_group" || return 1
  current_core_config_snapshot off "$(manifest_read canary-scope-sha256)" false \
    >/dev/null || return 1
  [ "$(cat "$release_lock_state")" = active ] || return 1
  write_lock_state failed
)

current_receipt_sha() (
  current="$release_receipt_root/current"
  [ -f "$current" ] && [ ! -L "$current" ] \
    && [ "$(private_mode "$current")" = 600 ] || {
      echo "durable-release:error:current-release-receipt-missing" >&2
      exit 1
    }
  sha="$(sed -n '1p' "$current")"
  [ "$(wc -l < "$current" | tr -d ' ')" = 1 ] || exit 1
  require_sha256 "$sha" current-release-receipt-sha256
  receipt_dir="$release_receipt_root/$sha"
  python3 "$receipt_helper" verify --receipt-dir "$receipt_dir" \
    --expected-sha256 "$sha" >/dev/null || {
      echo "durable-release:error:current-release-receipt-invalid" >&2
      exit 1
    }
  printf '%s\n' "$sha"
)

receipt_read() (
  receipt_sha="$1"
  field="$2"
  python3 "$receipt_helper" read --receipt-dir "$release_receipt_root/$receipt_sha" \
    --expected-sha256 "$receipt_sha" --field "$field"
)

verify_current_receipt_runtime() (
  receipt_sha="$(current_receipt_sha)"
  expected_web="$(receipt_read "$receipt_sha" web-digest)"
  expected_core="$(receipt_read "$receipt_sha" core-digest)"
  expected_agent="$(receipt_read "$receipt_sha" agent-digest)"
  expected_fingerprint="$(receipt_read "$receipt_sha" execution-manifest-fingerprint)"
  [ "$(current_service_digest web inkforge-web)" = "$expected_web" ] \
    && [ "$(current_service_digest core-api inkforge-core-api)" = "$expected_core" ] \
    && [ "$(current_service_digest agent-service inkforge-agent-service)" = "$expected_agent" ] || {
      echo "durable-release:error:current-receipt-runtime-digest-drift" >&2
      exit 1
    }
  sh "$image_verifier" core "$expected_core" >/dev/null
  probe="$(sh "$image_verifier" agent "$expected_agent" "$expected_fingerprint")" || exit 1
  parse_agent_probe "$probe" >/dev/null
  route="$(receipt_read "$receipt_sha" route-mode)"
  scope="$(receipt_read "$receipt_sha" canary-scope-sha256)"
  schema_ready="$(receipt_read "$receipt_sha" schema-ready)"
  v1_fresh="$(receipt_read "$receipt_sha" v1-fresh-starts-enabled)"
  runtime="$(current_core_config_snapshot "$route" "$scope" "$v1_fresh")"
  [ "$(printf '%s\n' "$runtime" | sed -n 's/^runtimeSchemaReady=//p')" = \
    "$schema_ready" ] || {
      echo "durable-release:error:current-receipt-schema-ready-drift" >&2
      exit 1
    }
  printf '%s\n' "$receipt_sha"
)

current_core_config_snapshot() (
  expected_route="$1"
  expected_scope="$2"
  expected_v1_fresh="${3:-any}"
  containers="$(docker ps -q \
    --filter label=com.docker.compose.project=inkforge \
    --filter label=com.docker.compose.service=core-api)" || exit 1
  # shellcheck disable=SC2086
  set -- $containers
  [ "$#" -eq 1 ] || {
    echo "durable-release:error:runtime-core-count" >&2
    exit 1
  }
  raw="$(docker exec "$1" /bin/sh -ec \
    'printf "%s\n%s\n%s\n%s\n%s\n" "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-off}" "${DURABLE_AGENT_EXECUTION_SCHEMA_READY:-false}" "${DURABLE_AGENT_EXECUTION_USER_ALLOWLIST:-}" "${DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST:-}" "${V1_FRESH_AGENT_STARTS_ENABLED:-true}"')" || {
      echo "durable-release:error:runtime-core-config" >&2
      exit 1
    }
  route="$(printf '%s\n' "$raw" | sed -n '1p')"
  schema_ready="$(printf '%s\n' "$raw" | sed -n '2p')"
  user_id="$(printf '%s\n' "$raw" | sed -n '3p')"
  novel_id="$(printf '%s\n' "$raw" | sed -n '4p')"
  v1_fresh="$(printf '%s\n' "$raw" | sed -n '5p')"
  [ "$(printf '%s\n' "$raw" | wc -l | tr -d ' ')" = 5 ] || {
    echo "durable-release:error:runtime-core-config-lines" >&2
    exit 1
  }
  [ "$expected_route" = any ] || [ "$route" = "$expected_route" ] || {
    echo "durable-release:error:runtime-route-drift" >&2
    exit 1
  }
  case "$schema_ready" in true|false) ;;
    *) echo "durable-release:error:runtime-schema-ready" >&2; exit 1 ;;
  esac
  case "$v1_fresh" in true|false) ;;
    *) echo "durable-release:error:runtime-v1-fresh" >&2; exit 1 ;;
  esac
  [ "$expected_v1_fresh" = any ] || [ "$v1_fresh" = "$expected_v1_fresh" ] || {
    echo "durable-release:error:runtime-v1-fresh-drift" >&2
    exit 1
  }
  [ "$route" != allowlist ] || [ "$schema_ready" = true ] || {
    echo "durable-release:error:allowlist-schema-not-ready" >&2
    exit 1
  }
  actual_scope="$(python3 - "$user_id" "$novel_id" <<'PY'
import hashlib
import json
import re
import sys

pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
user_id, novel_id = sys.argv[1:]
if not pattern.fullmatch(user_id) or not pattern.fullmatch(novel_id):
    raise SystemExit("scope-id")
payload = json.dumps(
    {"novelId": novel_id, "userId": user_id},
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode()
print(hashlib.sha256(payload).hexdigest())
PY
)" || {
    echo "durable-release:error:runtime-canary-scope" >&2
    exit 1
  }
  [ "$actual_scope" = "$expected_scope" ] || {
    echo "durable-release:error:runtime-canary-scope-drift" >&2
    exit 1
  }
  printf 'runtimeRoute=%s\n' "$route"
  printf 'runtimeSchemaReady=%s\n' "$schema_ready"
  printf 'runtimeV1FreshStartsEnabled=%s\n' "$v1_fresh"
  printf 'runtimeCanaryScopeSha256=%s\n' "$actual_scope"
)

verified_drain_path() {
  printf '%s\n' "$release_lock_dir/verified-drain.json"
}

verified_drain_report_path() {
  printf '%s\n' "$release_lock_dir/verified-drain-report.json"
}

capture_verified_drain() {
  require_release_lock
  require_control_bundle
  [ -r "$migration_helper" ] && [ -r "$boundary_helper" ] || {
    echo "durable-release:error:verified-drain-interface-missing" >&2
    exit 1
  }
  target_path="$(verified_drain_path)"
  report_path="$(verified_drain_report_path)"
  [ ! -e "$target_path" ] || {
    echo "durable-release:error:verified-drain-already-exists" >&2
    exit 1
  }
  [ ! -e "$report_path" ] || exit 1
  temporary="$release_lock_dir/.verified-drain-report.partial"
  [ ! -e "$temporary" ] || exit 1
  if ! run_migration_helper boundary-drain novelwriter > "$temporary"; then
    rm -f -- "$temporary"
    echo "durable-release:error:verified-drain-not-zero" >&2
    exit 1
  fi
  chmod 600 "$temporary"
  python3 "$boundary_helper" verify-live --live-report "$temporary" >/dev/null || {
    rm -f -- "$temporary"
    echo "durable-release:error:verified-drain-invalid" >&2
    exit 1
  }
  mv "$temporary" "$report_path"
  report_sha="$(sha256sum "$report_path" | cut -d ' ' -f 1)"
  migration_sha="$(sha256sum "$migration_helper" | cut -d ' ' -f 1)"
  verifier_sha="$(sha256sum "$boundary_helper" | cut -d ' ' -f 1)"
  python3 - "$report_path" "$target_path" "$workflow_commit" "$target_commit" \
    "$control_bundle_sha" "$migration_sha" "$verifier_sha" "$release_lock_id" \
    "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" "$report_sha" <<'PY'
import json
import os
import sys
from pathlib import Path

report_path, output_path = map(Path, sys.argv[1:3])
report = json.loads(report_path.read_text(encoding="utf-8"))
document = {
    "boundaryHelperSha256": sys.argv[7],
    "controlBundleSha256": sys.argv[5],
    "coreRuntime": report["coreRuntime"],
    "format": "inkforge-durable-agent-v2-verified-drain/1",
    "lockId": sys.argv[8],
    "migrationHelperSha256": sys.argv[6],
    "postgresIdentity": report["postgresIdentity"],
    "redisIdentity": report["redisIdentity"],
    "executionRedisIdentity": report["executionRedisIdentity"],
    "profile": report["mode"],
    "reportSha256": sys.argv[11],
    "runAttempt": sys.argv[10],
    "runId": sys.argv[9],
    "runtimeTopologySha256": report["runtimeTopologySha256"],
    "targetReleaseCommit": sys.argv[4],
    "workflowTrustedCommit": sys.argv[3],
}
payload = (
    json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    + "\n"
).encode()
descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as target:
    target.write(payload)
    target.flush()
    os.fsync(target.fileno())
PY
  sha256sum "$target_path" | cut -d ' ' -f 1
}

require_verified_drain() {
  expected="${VERIFIED_DRAIN_SHA256:-}"
  require_sha256 "$expected" verified-drain-sha256
  path="$(verified_drain_path)"
  report_path="$(verified_drain_report_path)"
  [ -f "$path" ] && [ ! -L "$path" ] \
    && [ "$(private_mode "$path")" = 600 ] || {
    echo "durable-release:error:verified-drain-evidence-missing" >&2
    exit 1
  }
  [ -f "$report_path" ] && [ ! -L "$report_path" ] \
    && [ "$(private_mode "$report_path")" = 600 ] \
    && [ "$(sha256sum "$path" | cut -d ' ' -f 1)" = "$expected" ] || {
    echo "durable-release:error:verified-drain-sha256" >&2
    exit 1
  }
  require_control_bundle
  python3 "$boundary_helper" verify-live --live-report "$report_path" >/dev/null || {
      echo "durable-release:error:verified-drain-reverify" >&2
      exit 1
    }
  python3 - "$path" "$report_path" "$workflow_commit" "$target_commit" \
    "$control_bundle_sha" "$migration_helper" "$boundary_helper" \
    "$release_lock_id" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

binding_path, report_path = map(Path, sys.argv[1:3])
binding = json.loads(binding_path.read_text(encoding="utf-8"))
report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
expected = {
    "boundaryHelperSha256": hashlib.sha256(Path(sys.argv[7]).read_bytes()).hexdigest(),
    "controlBundleSha256": sys.argv[5],
    "coreRuntime": json.loads(report_path.read_text(encoding="utf-8"))["coreRuntime"],
    "executionRedisIdentity": json.loads(report_path.read_text(encoding="utf-8"))["executionRedisIdentity"],
    "format": "inkforge-durable-agent-v2-verified-drain/1",
    "lockId": sys.argv[8],
    "migrationHelperSha256": hashlib.sha256(Path(sys.argv[6]).read_bytes()).hexdigest(),
    "postgresIdentity": json.loads(report_path.read_text(encoding="utf-8"))["postgresIdentity"],
    "profile": json.loads(report_path.read_text(encoding="utf-8"))["mode"],
    "redisIdentity": json.loads(report_path.read_text(encoding="utf-8"))["redisIdentity"],
    "reportSha256": report_sha,
    "runAttempt": sys.argv[10],
    "runId": sys.argv[9],
    "runtimeTopologySha256": json.loads(report_path.read_text(encoding="utf-8"))["runtimeTopologySha256"],
    "targetReleaseCommit": sys.argv[4],
    "workflowTrustedCommit": sys.argv[3],
}
canonical = (
    json.dumps(binding, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    + "\n"
).encode()
if binding != expected or binding_path.read_bytes() != canonical:
    raise SystemExit("verified-drain-binding")
PY
}

require_boundary_name() {
  case "$1" in
    compose-release|compose-rollback|allowlist-config|ddl-forward-[1-9]|ddl-forward-[1-9][0-9]*) ;;
    *) echo "durable-release:error:boundary-name" >&2; exit 2 ;;
  esac
}

boundary_runtime_group() {
  case "$1" in
    compose-release) printf 'rollback\n' ;;
    compose-rollback) printf 'target\n' ;;
    allowlist-config|ddl-forward-*) printf 'target\n' ;;
    *) exit 2 ;;
  esac
}

consume_live_boundary() (
  boundary="$1"
  require_boundary_name "$boundary"
  require_release_lock
  require_control_bundle
  verify_manifest
  [ -r "$boundary_helper" ] && [ -r "$migration_helper" ] || {
    echo "durable-release:error:boundary-helper-missing" >&2
    exit 1
  }
  runtime_group="$(boundary_runtime_group "$boundary")"
  case "$boundary" in compose-release|compose-rollback) write_release_guard off ;; esac
  EXPECTED_RUNTIME_ROUTE_MODE=off runtime_preflight "$runtime_group"
  if [ ! -e "$boundary_evidence_dir" ]; then
    mkdir "$boundary_evidence_dir"
    chmod 700 "$boundary_evidence_dir"
  fi
  [ -d "$boundary_evidence_dir" ] && [ ! -L "$boundary_evidence_dir" ] \
    && [ "$(private_mode "$boundary_evidence_dir")" = 700 ] || {
      echo "durable-release:error:boundary-evidence-dir" >&2
      exit 1
    }
  live="$release_lock_dir/.boundary-live-$boundary.partial"
  [ ! -e "$live" ] || {
    echo "durable-release:error:boundary-live-partial" >&2
    exit 1
  }
  if ! run_migration_helper boundary-drain novelwriter > "$live"; then
    rm -f -- "$live"
    echo "durable-release:error:boundary-live-drain" >&2
    exit 1
  fi
  chmod 600 "$live"
  python3 - "$live" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  python3 "$boundary_helper" verify-live --live-report "$live" >/dev/null || {
    rm -f -- "$live"
    echo "durable-release:error:boundary-live-invalid" >&2
    exit 1
  }
  boundary_helper_sha="$(sha256sum "$boundary_helper" | cut -d ' ' -f 1)"
  issue_output="$(python3 "$boundary_helper" issue \
    --live-report "$live" --evidence-dir "$boundary_evidence_dir" \
    --boundary "$boundary" --lock-id "$release_lock_id" \
    --control-bundle-sha256 "$control_bundle_sha" \
    --manifest-sha256 "$RELEASE_MANIFEST_SHA256" \
    --run-id "$GITHUB_RUN_ID" --run-attempt "$GITHUB_RUN_ATTEMPT" \
    --boundary-helper-sha256 "$boundary_helper_sha" \
    --workflow-trusted-commit "$workflow_commit" \
    --target-release-commit "$target_commit")" || {
      rm -f -- "$live"
      exit 1
    }
  rest="${issue_output#boundary-evidence-ready:}"
  [ "$rest" != "$issue_output" ] || exit 1
  sequence="${rest%%:*}"
  rest="${rest#*:}"
  evidence_sha="${rest%%:*}"
  ready="${rest#*:}"
  require_sha256 "$evidence_sha" boundary-evidence-sha256
  case "$sequence" in ''|*[!0-9]*) exit 1 ;; esac
  expected_ready="$boundary_evidence_dir/$(printf '%06d' "$sequence")-$boundary.ready.json"
  [ "$ready" = "$expected_ready" ] || exit 1
  claim_output="$(python3 "$boundary_helper" consume \
    --evidence-dir "$boundary_evidence_dir" --ready-file "$ready" \
    --expected-sha256 "$evidence_sha" --boundary "$boundary" \
    --lock-id "$release_lock_id" --control-bundle-sha256 "$control_bundle_sha" \
    --manifest-sha256 "$RELEASE_MANIFEST_SHA256" \
    --run-id "$GITHUB_RUN_ID" --run-attempt "$GITHUB_RUN_ATTEMPT" \
    --boundary-helper-sha256 "$boundary_helper_sha" \
    --workflow-trusted-commit "$workflow_commit" \
    --target-release-commit "$target_commit")" || exit 1
  claimed="$boundary_evidence_dir/$(printf '%06d' "$sequence")-$boundary.claimed.json"
  [ "$claim_output" = "boundary-evidence-claimed:$evidence_sha:$claimed" ] || exit 1
  rm -f -- "$live"
  printf 'live-boundary-claimed:%s:%s\n' "$boundary" "$evidence_sha"
)

mark_live_boundary_applied() (
  boundary="$1"
  require_boundary_name "$boundary"
  require_release_lock
  require_control_bundle
  verify_manifest
  outcome="${DURABLE_AGENT_BOUNDARY_OUTCOME:-succeeded}"
  case "$outcome" in succeeded|compensated) ;; *) exit 2 ;; esac
  # shellcheck disable=SC2086
  set -- "$boundary_evidence_dir/"[0-9][0-9][0-9][0-9][0-9][0-9]-"$boundary".claimed.json
  [ "$#" -eq 1 ] && [ -f "$1" ] && [ ! -L "$1" ] || {
    echo "durable-release:error:boundary-claimed-missing" >&2
    exit 1
  }
  claimed="$1"
  evidence_sha="$(sha256sum "$claimed" | cut -d ' ' -f 1)"
  boundary_helper_sha="$(sha256sum "$boundary_helper" | cut -d ' ' -f 1)"
  inject_release_fault boundary-before-applied
  output="$(python3 "$boundary_helper" mark-applied \
    --evidence-dir "$boundary_evidence_dir" --claimed-file "$claimed" \
    --expected-sha256 "$evidence_sha" --outcome "$outcome" \
    --boundary "$boundary" --lock-id "$release_lock_id" \
    --control-bundle-sha256 "$control_bundle_sha" \
    --manifest-sha256 "$RELEASE_MANIFEST_SHA256" \
    --run-id "$GITHUB_RUN_ID" --run-attempt "$GITHUB_RUN_ATTEMPT" \
    --boundary-helper-sha256 "$boundary_helper_sha" \
    --workflow-trusted-commit "$workflow_commit" \
    --target-release-commit "$target_commit")" || exit 1
  case "$output" in boundary-evidence-applied:*) ;;
    *) echo "durable-release:error:boundary-applied-output" >&2; exit 1 ;;
  esac
  printf 'live-boundary-applied:%s:%s\n' "$boundary" "$outcome"
)

build_boundary_ledger() (
  require_release_lock
  ledger="$release_lock_dir/boundary-ledger.json"
  [ ! -e "$ledger" ] || {
    echo "durable-release:error:boundary-ledger-already-exists" >&2
    exit 1
  }
  temporary="$release_lock_dir/.boundary-ledger.partial"
  [ ! -e "$temporary" ] || exit 1
  python3 "$boundary_helper" ledger --evidence-dir "$boundary_evidence_dir" \
    --lock-id "$release_lock_id" > "$temporary"
  chmod 600 "$temporary"
  python3 - "$temporary" "$RELEASE_ACTION" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
document = json.loads(path.read_text(encoding="utf-8"))
boundaries = [entry["boundary"] for entry in document["entries"]]
action = sys.argv[2]
required = "compose-rollback" if action == "rollback" else "compose-release"
if boundaries.count(required) != 1:
    raise SystemExit("missing-compose-boundary")
if action == "allowlist_release":
    if boundaries.count("allowlist-config") != 1:
        raise SystemExit("missing-allowlist-boundary")
elif "allowlist-config" in boundaries:
    raise SystemExit("unexpected-allowlist-boundary")
ddl = [value for value in boundaries if value.startswith("ddl-forward-")]
if ddl not in ([], ["ddl-forward-1", "ddl-forward-2"]):
    raise SystemExit("incomplete-ddl-boundary-pair")
descriptor = os.open(path, os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  mv "$temporary" "$ledger"
  ledger_sha="$(sha256sum "$ledger" | cut -d ' ' -f 1)"
  require_sha256 "$ledger_sha" boundary-ledger-sha256
  printf '%s\n' "$ledger_sha"
)

write_release_guard() (
  guard_state="$1"
  committed_receipt="${2:-}"
  [ -r "$guard_helper" ] && [ -r "$guard_compose_file" ] || {
    echo "durable-release:error:guard-control-missing" >&2
    exit 1
  }
  case "$guard_state" in
    off)
      python3 "$guard_helper" write --path "$release_guard_file" --state off \
        >/dev/null
      ;;
    pending|committed)
      require_release_lock
      verify_manifest
      lease_file="$release_lock_dir/allowlist-lease-id"
      if [ "$guard_state" = pending ]; then
        [ ! -e "$lease_file" ] || {
          echo "durable-release:error:pending-lease-nonrenewable" >&2
          exit 1
        }
        python3 - "$lease_file" <<'PY'
import os
import secrets
import sys

descriptor = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as output:
    output.write(secrets.token_hex(32) + "\n")
    output.flush()
    os.fsync(output.fileno())
PY
      else
        [ -f "$lease_file" ] && [ ! -L "$lease_file" ] || {
          echo "durable-release:error:committed-lease-missing" >&2
          exit 1
        }
      fi
      lease_id="$(cat "$lease_file")"
      require_sha256 "$lease_id" release-guard-lease-id
      fingerprint="$(manifest_read target-manifest-fingerprint)"
      scope="$(manifest_read canary-scope-sha256)"
      set -- python3 "$guard_helper" write --path "$release_guard_file" \
        --state "$guard_state" --canary-scope-sha256 "$scope" \
        --control-bundle-sha256 "$control_bundle_sha" \
        --execution-manifest-fingerprint "$fingerprint" \
        --lease-id "$lease_id" --lock-id "$release_lock_id" \
        --manifest-sha256 "$RELEASE_MANIFEST_SHA256" \
        --run-attempt "$GITHUB_RUN_ATTEMPT" --run-id "$GITHUB_RUN_ID"
      if [ "$guard_state" = committed ]; then
        require_sha256 "$committed_receipt" committed-receipt-sha256
        set -- "$@" --committed-receipt-sha256 "$committed_receipt"
      fi
      "$@" >/dev/null
      ;;
    *) exit 2 ;;
  esac
  python3 "$guard_helper" verify --path "$release_guard_file" >/dev/null
)

restore_env_snapshot() (
  snapshot="${1:-$release_lock_dir/env.before}"
  verify_env_snapshot "$snapshot" || return 1
  temporary="$release_lock_dir/.env.restore.partial"
  [ ! -e "$temporary" ] || return 1
  python3 - "$snapshot" "$app_dir/.env" "$temporary" <<'PY'
import os
import shutil
import sys
from pathlib import Path

source, target, temporary = map(Path, sys.argv[1:])
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
    shutil.copyfileobj(input_file, output)
    output.flush()
    os.fsync(output.fileno())
os.replace(temporary, target)
directory = os.open(target.parent, os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
)

transition_runtime_config() (
  transition_wanted="$1"
  case "$transition_wanted" in
    off) transition_wanted_route=off; transition_schema_ready=keep; transition_v1_fresh=false ;;
    schema-ready-off) transition_wanted_route=off; transition_schema_ready=true; transition_v1_fresh=false ;;
    allowlist) transition_wanted_route=allowlist; transition_schema_ready=true; transition_v1_fresh=true ;;
    *) exit 2 ;;
  esac
  require_release_lock
  verify_manifest
  transition_env_file="$app_dir/.env"
  [ -f "$transition_env_file" ] && [ ! -L "$transition_env_file" ] || {
    echo "durable-release:error:runtime-env" >&2
    exit 1
  }
  transition_scope="$(manifest_read canary-scope-sha256)"
  transition_user_id="${CANARY_USER_ID:-}"
  transition_novel_id="${CANARY_NOVEL_ID:-}"
  if [ -z "$transition_user_id" ] || [ -z "$transition_novel_id" ]; then
    transition_existing="$(python3 - "$transition_env_file" <<'PY'
import sys
from pathlib import Path

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    key = key.strip()
    if key in {"DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST"}:
        if key in values:
            raise SystemExit("duplicate")
        values[key] = value.strip().strip("'\"")
print(values.get("DURABLE_AGENT_EXECUTION_USER_ALLOWLIST", ""))
print(values.get("DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST", ""))
PY
)" || exit 1
    transition_user_id="$(printf '%s\n' "$transition_existing" | sed -n '1p')"
    transition_novel_id="$(printf '%s\n' "$transition_existing" | sed -n '2p')"
  fi
  transition_calculated_scope="$(python3 - "$transition_user_id" \
    "$transition_novel_id" <<'PY'
import hashlib
import json
import re
import sys

pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
user_id, novel_id = sys.argv[1:]
if not pattern.fullmatch(user_id) or not pattern.fullmatch(novel_id):
    raise SystemExit("scope")
payload = json.dumps(
    {"novelId": novel_id, "userId": user_id},
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode()
print(hashlib.sha256(payload).hexdigest())
PY
)" || exit 1
  [ "$transition_calculated_scope" = "$transition_scope" ] || {
    echo "durable-release:error:transition-canary-scope" >&2
    exit 1
  }
  transition_before="$release_lock_dir/env.before"
  if [ "$transition_wanted" = allowlist ]; then
    transition_before="$release_lock_dir/env.allowlist.before"
  fi
  if [ ! -e "$transition_before" ]; then
    python3 - "$transition_env_file" "$transition_before" <<'PY'
import os
import shutil
import sys
from pathlib import Path

source, target = map(Path, sys.argv[1:])
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
    shutil.copyfileobj(input_file, output)
    output.flush()
    os.fsync(output.fileno())
PY
    transition_before_sha_file="$release_lock_dir/$(basename "$transition_before").sha256"
    transition_before_sha="$(sha256sum "$transition_before" | cut -d ' ' -f 1)"
    require_sha256 "$transition_before_sha" env-snapshot-sha256
    python3 - "$transition_before_sha_file" "$transition_before_sha" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as output:
    output.write(sys.argv[2] + "\n")
    output.flush()
    os.fsync(output.fileno())
PY
  fi
  verify_env_snapshot "$transition_before" || {
    echo "durable-release:error:runtime-env-snapshot" >&2
    exit 1
  }
  transition_env_temporary="$release_lock_dir/.env.transition.partial"
  [ ! -e "$transition_env_temporary" ] || exit 1
  python3 - "$transition_env_file" "$transition_env_temporary" \
    "$transition_wanted_route" \
    "$transition_schema_ready" "$transition_v1_fresh" \
    "$transition_user_id" "$transition_novel_id" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
temporary = Path(sys.argv[2])
wanted, schema_ready, v1_fresh, user_id, novel_id = sys.argv[3:]
updates = {
    "DURABLE_AGENT_EXECUTION_ROUTE_MODE": wanted,
    "DURABLE_AGENT_EXECUTION_USER_ALLOWLIST": user_id,
    "DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST": novel_id,
    "V1_FRESH_AGENT_STARTS_ENABLED": v1_fresh,
}
if schema_ready != "keep":
    updates["DURABLE_AGENT_EXECUTION_SCHEMA_READY"] = schema_ready
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
output = []
for raw in lines:
    if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
        output.append(raw)
        continue
    key, _value = raw.split("=", 1)
    key = key.strip()
    if key not in updates:
        output.append(raw)
        continue
    if key in seen:
        raise SystemExit("duplicate-rollout-key")
    seen.add(key)
    output.append(f"{key}={updates[key]}")
for key in sorted(set(updates) - seen):
    output.append(f"{key}={updates[key]}")
payload = ("\n".join(output) + "\n").encode()
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as target:
    target.write(payload)
    target.flush()
    os.fsync(target.fileno())
PY
  if [ "$transition_wanted" = allowlist ]; then
    (consume_live_boundary allowlist-config >/dev/null)
    (write_release_guard pending)
  else
    (write_release_guard off)
  fi
  python3 - "$transition_env_file" "$transition_env_temporary" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
temporary = Path(sys.argv[2])
os.replace(temporary, path)
directory = os.open(path.parent, os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
  transition_before_core="$(current_service_digest core-api inkforge-core-api)"
  transition_tag="control-${release_lock_id}"
  docker image tag "$transition_before_core" \
    "inkforge-core-api:$transition_tag" >/dev/null
  transition_status=0
  (
    export DURABLE_AGENT_RELEASE_GUARD_HOST_DIR="$release_guard_root"
    INKFORGE_IMAGE_TAG="$transition_tag" \
    SERVICE_KEYS_DIR="$app_dir/infra/secrets" docker compose \
      --env-file "$transition_env_file" --project-directory "$control_dir/infra" \
      -f "$control_dir/infra/compose.yaml" -f "$guard_compose_file" \
      up --no-build -d --wait --no-deps \
      --force-recreate core-api || exit $?
    transition_after_core="$(current_service_digest core-api inkforge-core-api)"
    [ "$transition_after_core" = "$transition_before_core" ]
    current_core_config_snapshot "$transition_wanted_route" "$transition_scope" \
      "$transition_v1_fresh" >/dev/null
  ) || transition_status=$?
  if [ "$transition_status" -ne 0 ]; then
    (write_release_guard off) || true
    transition_fail_closed="${DURABLE_AGENT_TRANSITION_FAIL_CLOSED:-false}"
    case "$transition_fail_closed:$transition_wanted_route" in
      true:off) ;;
      false:off|false:allowlist) (restore_env_snapshot "$transition_before") || true ;;
      *) echo "durable-release:error:transition-failure-policy" >&2; exit 1 ;;
    esac
    DURABLE_AGENT_RELEASE_GUARD_HOST_DIR="$release_guard_root" \
    INKFORGE_IMAGE_TAG="$transition_tag" \
    SERVICE_KEYS_DIR="$app_dir/infra/secrets" docker compose \
      --env-file "$transition_env_file" --project-directory "$control_dir/infra" \
      -f "$control_dir/infra/compose.yaml" -f "$guard_compose_file" \
      up --no-build -d --wait --no-deps \
      --force-recreate core-api >/dev/null 2>&1 || true
    echo "durable-release:error:transition-core-restart" >&2
    exit "$transition_status"
  fi
  if [ "$transition_wanted" = allowlist ]; then
    (mark_live_boundary_applied allowlist-config >/dev/null)
  fi
  transition_after_core="$transition_before_core"
  {
    printf 'routeMode=%s\n' "$transition_wanted_route"
    printf 'coreDigest=%s\n' "$transition_after_core"
    printf 'canaryScopeSha256=%s\n' "$transition_scope"
  } > "$release_lock_dir/runtime-config-transition"
  chmod 600 "$release_lock_dir/runtime-config-transition"
  printf 'runtime-config-transition-ok:%s\n' "$transition_wanted"
)

prepare_release_receipt() (
  require_release_lock
  require_sha256 "${RELEASE_MANIFEST_SHA256:-}" release-manifest-sha256
  boundary_ledger_sha="$(build_boundary_ledger)"
  previous_receipt="$(current_receipt_sha)"
  base_receipt="$(cat "$release_lock_dir/base-receipt.sha256")"
  require_sha256 "$base_receipt" base-receipt-sha256
  [ "$previous_receipt" = "$base_receipt" ] || {
    echo "durable-release:error:receipt-base-cas" >&2
    exit 1
  }
  case "$RELEASE_ACTION" in
    route_off_release|allowlist_release)
      active_commit="$target_commit"
      image_group=target
      runtime_group=target
      ;;
    rollback)
      active_commit="$(manifest_read rollback-source-release-commit)"
      image_group=rollback
      runtime_group=rollback
      ;;
  esac
  expected_route=off
  [ "$RELEASE_ACTION" != allowlist_release ] || expected_route=allowlist
  EXPECTED_RUNTIME_ROUTE_MODE="$expected_route" runtime_preflight "$runtime_group"
  scope="$(manifest_read canary-scope-sha256)"
  runtime="$(current_core_config_snapshot "$expected_route" "$scope" any)"
  schema_ready="$(printf '%s\n' "$runtime" | sed -n 's/^runtimeSchemaReady=//p')"
  v1_fresh="$(printf '%s\n' "$runtime" | sed -n 's/^runtimeV1FreshStartsEnabled=//p')"
  web_digest="$(current_service_digest web inkforge-web)"
  core_digest="$(current_service_digest core-api inkforge-core-api)"
  agent_digest="$(current_service_digest agent-service inkforge-agent-service)"
  core_container="$(docker ps -q --filter label=com.docker.compose.project=inkforge \
    --filter label=com.docker.compose.service=core-api)"
  # shellcheck disable=SC2086
  set -- $core_container
  [ "$#" -eq 1 ] || exit 1
  core_container="$1"
  fingerprint="$(manifest_read "$image_group-manifest-fingerprint")"
  candidate="$release_lock_dir/release-receipt-candidate"
  [ ! -e "$candidate" ] || exit 1
  inject_release_fault receipt-create
  python3 "$receipt_helper" create --output-dir "$candidate" \
    --active-release-commit "$active_commit" \
    --agent-digest "$agent_digest" --canary-scope-sha256 "$scope" \
    --control-bundle-sha256 "$control_bundle_sha" \
    --core-container-id "$core_container" --core-digest "$core_digest" \
    --boundary-ledger-sha256 "$boundary_ledger_sha" \
    --execution-manifest-fingerprint "$fingerprint" \
    --lock-id "$release_lock_id" --manifest-sha256 "$RELEASE_MANIFEST_SHA256" \
    --previous-receipt-sha256 "$previous_receipt" \
    --release-action "$RELEASE_ACTION" --route-mode "$expected_route" \
    --run-attempt "$GITHUB_RUN_ATTEMPT" --run-id "$GITHUB_RUN_ID" \
    --schema-ready "$schema_ready" --target-release-commit "$target_commit" \
    --v1-fresh-starts-enabled "$v1_fresh" --web-digest "$web_digest" \
    --workflow-trusted-commit "$workflow_commit" >/dev/null
  inject_release_fault receipt-candidate-created
  receipt_sha="$(sha256sum "$candidate/release-receipt.json" | cut -d ' ' -f 1)"
  require_sha256 "$receipt_sha" sealed-release-receipt-sha
  mkdir -p "$release_receipt_root"
  chmod 700 "$release_receipt_root"
  final="$release_receipt_root/$receipt_sha"
  if [ -e "$final" ]; then
    python3 "$receipt_helper" verify --receipt-dir "$final" \
      --expected-sha256 "$receipt_sha" >/dev/null
    rm -f -- "$candidate/release-receipt.json" "$candidate/SHA256SUMS"
    rmdir "$candidate"
  else
    inject_release_fault receipt-before-publish
    output="$(python3 "$receipt_helper" publish --receipt-dir "$candidate" \
      --target-dir "$final" --expected-sha256 "$receipt_sha")" || exit 1
    [ "$output" = "release-receipt-published:$receipt_sha" ] \
      && [ -d "$final" ] && [ ! -e "$candidate" ] || exit 1
  fi
  inject_release_fault receipt-published
  write_private_line_no_replace \
    "$release_lock_dir/expected-receipt.sha256" "$receipt_sha"
  python3 - "$release_lock_dir/receipt-intent.json" "$base_receipt" \
    "$receipt_sha" "$release_lock_id" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" \
    "$RELEASE_ACTION" "$RELEASE_MANIFEST_SHA256" "$control_bundle_sha" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
document = {
    "baseReceiptSha256": sys.argv[2],
    "controlBundleSha256": sys.argv[9],
    "expectedReceiptSha256": sys.argv[3],
    "format": "inkforge-durable-agent-v2-receipt-intent/1",
    "lockId": sys.argv[4],
    "manifestSha256": sys.argv[8],
    "releaseAction": sys.argv[7],
    "runAttempt": sys.argv[6],
    "runId": sys.argv[5],
}
payload = (
    json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    + "\n"
).encode()
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as output:
    output.write(payload)
    output.flush()
    os.fsync(output.fileno())
directory = os.open(path.parent, os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
  write_lock_state prepared
  printf '%s\n' "$receipt_sha"
)

verify_expected_receipt_owner() (
  expected="$1"
  python3 "$receipt_helper" verify \
    --receipt-dir "$release_receipt_root/$expected" \
    --expected-sha256 "$expected" >/dev/null || return 1
  [ "$(receipt_read "$expected" manifest-sha256)" = "$RELEASE_MANIFEST_SHA256" ] \
    && [ "$(receipt_read "$expected" control-bundle-sha256)" = \
      "$control_bundle_sha" ]
)

receipt_commit_status() (
  base_file="$release_lock_dir/base-receipt.sha256"
  expected_file="$release_lock_dir/expected-receipt.sha256"
  [ -f "$base_file" ] && [ ! -L "$base_file" ] || {
    printf 'ambiguous\n'; return 0;
  }
  base="$(cat "$base_file")"
  require_sha256 "$base" base-receipt-sha256
  if [ ! -f "$expected_file" ] || [ -L "$expected_file" ]; then
    current="$(current_receipt_sha 2>/dev/null)" || {
      printf 'ambiguous\n'; return 0;
    }
    [ "$current" = "$base" ] && printf 'precommit\n' || printf 'ambiguous\n'
    return 0
  fi
  expected="$(cat "$expected_file")"
  require_sha256 "$expected" expected-receipt-sha256
  current="$(current_receipt_sha 2>/dev/null)" || {
    printf 'ambiguous\n'; return 0;
  }
  if [ "$current" = "$expected" ]; then
    if ! verify_expected_receipt_owner "$expected" \
      || ! verify_current_receipt_runtime >/dev/null 2>&1; then
      printf 'ambiguous-advanced\n'
      return 0
    fi
    if [ -f "$release_lock_dir/receipt-commit-confirmed" ] \
      && [ ! -L "$release_lock_dir/receipt-commit-confirmed" ] \
      && [ "$(cat "$release_lock_dir/receipt-commit-confirmed")" = "$expected" ]; then
      printf 'committed\n'
      return 0
    fi
    # current 已精确指向本事务不可变 candidate，且 owner/runtime 都复验成功。
    # 即便上次进程在 parent fsync/确认 marker 前退出，也只能继续完成 commit，
    # 绝不能把 current 倒退或把 allowlist 改回 off。
    printf 'commit-recoverable\n'
    return 0
  fi
  [ "$current" = "$base" ] && printf 'precommit\n' || printf 'ambiguous\n'
)

inject_release_fault() {
  point="$1"
  [ "${DURABLE_AGENT_RELEASE_FAULT_POINT:-}" != "$point" ] || {
    [ "${INKFORGE_LOCAL_RELEASE_TEST_MODE:-}" = true ] || {
      echo "durable-release:error:production-fault-injection-disabled" >&2
      exit 1
    }
    echo "durable-release:test-fault:$point" >&2
    exit 90
  }
}

confirm_current_receipt_commit() (
  expected="$(cat "$release_lock_dir/expected-receipt.sha256")"
  require_sha256 "$expected" expected-receipt-sha256
  [ "$(current_receipt_sha)" = "$expected" ] \
    && verify_expected_receipt_owner "$expected" \
    && verify_current_receipt_runtime >/dev/null || return 1
  python3 - "$release_receipt_root" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  inject_release_fault after-current-root-fsync
  [ "$(current_receipt_sha)" = "$expected" ] \
    && verify_expected_receipt_owner "$expected" \
    && verify_current_receipt_runtime >/dev/null || return 1
  inject_release_fault after-current-reread
  rm -f -- "$release_lock_dir/receipt-current-unfsynced"
  python3 - "$release_lock_dir" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  confirmed="$release_lock_dir/receipt-commit-confirmed"
  if [ -e "$confirmed" ]; then
    [ -f "$confirmed" ] && [ ! -L "$confirmed" ] \
      && [ "$(cat "$confirmed")" = "$expected" ] || return 1
  else
    write_private_line_no_replace "$confirmed" "$expected"
  fi
  write_lock_state committed_cleanup_pending
)

commit_prepared_receipt() (
  require_release_lock
  [ "$(cat "$release_lock_state")" = prepared ] || exit 1
  base="$(cat "$release_lock_dir/base-receipt.sha256")"
  expected="$(cat "$release_lock_dir/expected-receipt.sha256")"
  require_sha256 "$base" base-receipt-sha256
  require_sha256 "$expected" expected-receipt-sha256
  [ "$(current_receipt_sha)" = "$base" ] || exit 1
  verify_expected_receipt_owner "$expected" || exit 1
  current_partial="$release_lock_dir/.current-receipt.partial"
  write_private_line_no_replace "$current_partial" "$expected"
  inject_release_fault current-temp-written
  write_private_line_no_replace \
    "$release_lock_dir/receipt-current-unfsynced" "$expected"
  inject_release_fault before-current-replace
  python3 - "$release_receipt_root/current" "$current_partial" <<'PY'
import os
import sys

os.replace(sys.argv[2], sys.argv[1])
PY
  inject_release_fault after-current-replace
  confirm_current_receipt_commit
  [ "$(receipt_commit_status)" = committed ] || exit 1
  inject_release_fault after-commit-point
  printf '%s\n' "$expected"
)

finalize_committed_transaction() (
  require_release_lock
  [ "$(receipt_commit_status)" = committed ] || {
    echo "durable-release:error:finalize-not-committed" >&2
    exit 1
  }
  expected="$(cat "$release_lock_dir/expected-receipt.sha256")"
  if [ "$RELEASE_ACTION" = allowlist_release ]; then
    write_release_guard committed "$expected"
  else
    write_release_guard off
  fi
  write_lock_state committed_cleanup_pending
  inject_release_fault before-lock-cleanup
  python3 - "$release_lock_dir" <<'PY'
import re
import stat
import sys
from pathlib import Path

directory = Path(sys.argv[1])
allowed_files = {
    "base-receipt.sha256",
    "boundary-ledger.json",
    "env.allowlist.before",
    "env.allowlist.before.sha256",
    "env.before",
    "env.before.sha256",
    "expected-receipt.sha256",
    "allowlist-lease-id",
    "owner",
    "receipt-commit-confirmed",
    "receipt-intent.json",
    "runtime-config-transition",
    "state",
    "verified-drain-report.json",
    "verified-drain.json",
}
children = {path.name: path for path in directory.iterdir()}
if set(children) - allowed_files - {"boundary-evidence"}:
    raise SystemExit("lock-directory-extra-files")
for name, path in children.items():
    if path.is_symlink():
        raise SystemExit("lock-directory-symlink")
    if name in allowed_files:
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SystemExit("lock-directory-file")
        continue
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise SystemExit("boundary-directory")
    for item in path.iterdir():
        if item.is_symlink() or not item.is_file() or stat.S_IMODE(item.stat().st_mode) != 0o600:
            raise SystemExit("boundary-ledger-file")
        if item.name != "sequence" and re.fullmatch(
            r"[0-9]{6}-(?:compose-release|compose-rollback|allowlist-config|ddl-forward-[1-9][0-9]*)\.(?:claimed|applied)\.json",
            item.name,
        ) is None:
            raise SystemExit("boundary-ledger-name")
PY
  if [ -d "$boundary_evidence_dir" ]; then
    for path in "$boundary_evidence_dir"/*; do
      [ ! -e "$path" ] || rm -f -- "$path"
    done
    rmdir "$boundary_evidence_dir"
  fi
  for path in \
    "$release_lock_dir/base-receipt.sha256" \
    "$release_lock_dir/boundary-ledger.json" \
    "$release_lock_dir/env.before" "$release_lock_dir/env.before.sha256" \
    "$release_lock_dir/env.allowlist.before" \
    "$release_lock_dir/env.allowlist.before.sha256" \
    "$release_lock_dir/expected-receipt.sha256" \
    "$release_lock_dir/allowlist-lease-id" \
    "$release_lock_dir/receipt-commit-confirmed" \
    "$release_lock_dir/receipt-intent.json" \
    "$release_lock_dir/runtime-config-transition" \
    "$(verified_drain_path)" "$(verified_drain_report_path)" \
    "$release_lock_state" "$release_lock_owner"
  do
    [ ! -e "$path" ] || rm -f -- "$path"
  done
  rmdir "$release_lock_dir"
  rm -f -- "$release_lock_file"
  printf 'release-transaction-committed:%s\n' "$release_lock_id"
)

force_allowlist_route_off() (
  write_release_guard off || return 1
  DURABLE_AGENT_TRANSITION_FAIL_CLOSED=true transition_runtime_config off || return 1
  current_core_config_snapshot off "$(manifest_read canary-scope-sha256)" false \
    >/dev/null
)

reconcile_transaction_internal() (
  status="$(receipt_commit_status)"
  case "$status" in
    committed)
      expected="$(cat "$release_lock_dir/expected-receipt.sha256")"
      write_lock_state committed_cleanup_pending
      if [ "$RELEASE_ACTION" = allowlist_release ]; then
        write_release_guard committed "$expected" || return 1
      fi
      finalize_committed_transaction
      ;;
    commit-recoverable)
      confirm_current_receipt_commit || return 1
      expected="$(cat "$release_lock_dir/expected-receipt.sha256")"
      if [ "$RELEASE_ACTION" = allowlist_release ]; then
        write_release_guard committed "$expected" || return 1
      fi
      finalize_committed_transaction
      ;;
    precommit)
      if [ "$RELEASE_ACTION" = allowlist_release ]; then
        force_allowlist_route_off || return 1
      fi
      write_lock_state failed
      return 1
      ;;
    ambiguous)
      if [ "$RELEASE_ACTION" = allowlist_release ]; then
        force_allowlist_route_off || return 1
      fi
      write_lock_state failed
      return 1
      ;;
    ambiguous-advanced)
      # current 已前进但其 receipt/runtime 不能精确复验，结果未知；保持路由、
      # current 与锁不动，等待同 owner 的具名恢复，绝不能伪造 failed。
      return 1
      ;;
    *) return 1 ;;
  esac
)

allowlist_failure_trap() {
  original_status="$1"
  trap - EXIT HUP INT TERM
  set +e
  if reconcile_transaction_internal; then
    exit 0
  fi
  exit "$original_status"
}

finalize_allowlist_transaction() {
  require_release_lock
  [ "$RELEASE_ACTION" = allowlist_release ] || exit 2
  trap 'allowlist_failure_trap "$?"' EXIT
  trap 'allowlist_failure_trap 129' HUP
  trap 'allowlist_failure_trap 130' INT
  trap 'allowlist_failure_trap 143' TERM
  transition_runtime_config allowlist >/dev/null
  run_rollout_gate allowlist novelwriter
  prepare_release_receipt >/dev/null
  receipt_sha="$(commit_prepared_receipt)"
  write_release_guard committed "$receipt_sha"
  finalize_committed_transaction
  trap - EXIT HUP INT TERM
}

case "$action" in
  source-guard)
    [ -z "$argument" ] || exit 2
    require_source_guard
    printf 'source-guard-ok:%s\n' "$workflow_commit"
    ;;

  target-snapshot)
    [ -z "$argument" ] || exit 2
    require_source_guard
    require_release_files
    require_manifest_helper
    command -v docker >/dev/null 2>&1 || exit 1
    target_web="$(canonical_image_id "inkforge-web:$target_commit")"
    target_core="$(canonical_image_id "inkforge-core-api:$target_commit")"
    target_agent="$(canonical_image_id "inkforge-agent-service:$target_commit")"
    source_fingerprint="$(python3 "$manifest_helper" source-fingerprint \
      --repository-root "$app_dir")"
    sh "$image_verifier" core "$target_core" >/dev/null
    target_probe="$(sh "$image_verifier" agent "$target_agent" "$source_fingerprint")"
    target_fingerprint="$(parse_agent_probe "$target_probe")"
    printf 'targetWebDigest=%s\n' "$target_web"
    printf 'targetCoreDigest=%s\n' "$target_core"
    printf 'targetAgentDigest=%s\n' "$target_agent"
    printf 'targetManifestFingerprint=%s\n' "$target_fingerprint"
    ;;

  begin-snapshot)
    [ -z "$argument" ] || exit 2
    begin_release_lock
    require_image_verifier
    command -v docker >/dev/null 2>&1 || exit 1
    requested_scope="${CANARY_SCOPE_SHA256:-}"
    require_nonempty "$requested_scope" canary-scope-sha256
    require_sha256 "$requested_scope" canary-scope-sha256
    receipt_sha="$(verify_current_receipt_runtime)"
    write_private_line_no_replace "$release_lock_dir/base-receipt.sha256" "$receipt_sha"
    rollback_web="$(receipt_read "$receipt_sha" web-digest)"
    rollback_core="$(receipt_read "$receipt_sha" core-digest)"
    rollback_agent="$(receipt_read "$receipt_sha" agent-digest)"
    rollback_fingerprint="$(receipt_read "$receipt_sha" execution-manifest-fingerprint)"
    rollback_source_commit="$(receipt_read "$receipt_sha" active-release-commit)"
    runtime_route="$(receipt_read "$receipt_sha" route-mode)"
    runtime_schema_ready="$(receipt_read "$receipt_sha" schema-ready)"
    runtime_v1_fresh="$(receipt_read "$receipt_sha" v1-fresh-starts-enabled)"
    runtime_scope="$(receipt_read "$receipt_sha" canary-scope-sha256)"
    printf 'rollbackWebDigest=%s\n' "$rollback_web"
    printf 'rollbackCoreDigest=%s\n' "$rollback_core"
    printf 'rollbackAgentDigest=%s\n' "$rollback_agent"
    printf 'rollbackManifestFingerprint=%s\n' "$rollback_fingerprint"
    printf 'rollbackSourceReleaseCommit=%s\n' "$rollback_source_commit"
    printf 'rollbackSourceReceiptSha256=%s\n' "$receipt_sha"
    printf 'runtimeRoute=%s\n' "$runtime_route"
    printf 'runtimeSchemaReady=%s\n' "$runtime_schema_ready"
    printf 'runtimeV1FreshStartsEnabled=%s\n' "$runtime_v1_fresh"
    printf 'runtimeCanaryScopeSha256=%s\n' "$runtime_scope"
    ;;

  begin-rollback)
    [ -z "$argument" ] || exit 2
    require_release_files
    verify_manifest
    rollback_requested_commit="${ROLLBACK_SOURCE_RELEASE_COMMIT:-}"
    require_nonempty "$rollback_requested_commit" rollback-source-release-commit
    [ "$(manifest_read rollback-source-release-commit)" = \
      "$rollback_requested_commit" ] || {
        echo "durable-release:error:rollback-source-commit-drift" >&2
        exit 1
      }
    begin_release_lock
    current_receipt="$(verify_current_receipt_runtime)"
    write_private_line_no_replace \
      "$release_lock_dir/base-receipt.sha256" "$current_receipt"
    rollback_manifest_sha="${RELEASE_MANIFEST_SHA256:-}"
    require_nonempty "$rollback_manifest_sha" release-manifest-sha256
    [ "$(receipt_read "$current_receipt" active-release-commit)" = "$target_commit" ] \
      && [ "$(receipt_read "$current_receipt" manifest-sha256)" = \
        "$rollback_manifest_sha" ] || {
        echo "durable-release:error:rollback-current-receipt" >&2
        exit 1
      }
    source_receipt="$(manifest_read rollback-source-receipt-sha256)"
    [ "$(receipt_read "$current_receipt" previous-receipt-sha256)" = \
      "$source_receipt" ] || {
        echo "durable-release:error:rollback-receipt-chain" >&2
        exit 1
      }
    python3 "$receipt_helper" verify \
      --receipt-dir "$release_receipt_root/$source_receipt" \
      --expected-sha256 "$source_receipt" >/dev/null || {
        echo "durable-release:error:rollback-source-receipt" >&2
        exit 1
      }
    [ "$(receipt_read "$source_receipt" active-release-commit)" = \
      "$ROLLBACK_SOURCE_RELEASE_COMMIT" ] \
      && [ "$(receipt_read "$source_receipt" web-digest)" = \
        "$(manifest_read rollback-web-digest)" ] \
      && [ "$(receipt_read "$source_receipt" core-digest)" = \
        "$(manifest_read rollback-core-digest)" ] \
      && [ "$(receipt_read "$source_receipt" agent-digest)" = \
        "$(manifest_read rollback-agent-digest)" ] || {
        echo "durable-release:error:rollback-source-receipt-drift" >&2
        exit 1
      }
    runtime_preflight target
    printf 'begin-rollback-ok:%s\n' "$current_receipt"
    ;;

  create-manifest)
    [ -z "$argument" ] || exit 2
    require_production_approval
    require_source_guard
    require_control_bundle
    require_release_files
    require_manifest_helper
    target_snapshot="${TARGET_IMAGE_SNAPSHOT_FILE:-}"
    rollback_snapshot="${ROLLBACK_IMAGE_SNAPSHOT_FILE:-}"
    require_nonempty "$target_snapshot" target-image-snapshot-file
    require_nonempty "$rollback_snapshot" rollback-image-snapshot-file
    target_web="$(snapshot_value "$target_snapshot" target targetWebDigest)"
    target_core="$(snapshot_value "$target_snapshot" target targetCoreDigest)"
    target_agent="$(snapshot_value "$target_snapshot" target targetAgentDigest)"
    target_fingerprint="$(snapshot_value \
      "$target_snapshot" target targetManifestFingerprint)"
    rollback_web="$(snapshot_value "$rollback_snapshot" rollback rollbackWebDigest)"
    rollback_core="$(snapshot_value "$rollback_snapshot" rollback rollbackCoreDigest)"
    rollback_agent="$(snapshot_value "$rollback_snapshot" rollback rollbackAgentDigest)"
    rollback_fingerprint="$(snapshot_value \
      "$rollback_snapshot" rollback rollbackManifestFingerprint)"
    rollback_source_commit="$(snapshot_value \
      "$rollback_snapshot" rollback rollbackSourceReleaseCommit)"
    rollback_source_receipt_sha="$(snapshot_value \
      "$rollback_snapshot" rollback rollbackSourceReceiptSha256)"
    canary_scope="${CANARY_SCOPE_SHA256:-}"
    require_nonempty "$canary_scope" canary-scope-sha256
    require_sha256 "$canary_scope" canary-scope-sha256
    require_exact_image "inkforge-web:$target_commit" "$target_web"
    require_exact_image "inkforge-core-api:$target_commit" "$target_core"
    require_exact_image "inkforge-agent-service:$target_commit" "$target_agent"
    source_fingerprint="$(python3 "$manifest_helper" source-fingerprint \
      --repository-root "$app_dir")"
    [ "$target_fingerprint" = "$source_fingerprint" ] || {
      echo "durable-release:error:source-target-fingerprint" >&2
      exit 1
    }
    sh "$image_verifier" core "$target_core" >/dev/null
    sh "$image_verifier" agent "$target_agent" "$target_fingerprint" >/dev/null
    route_mode="${RELEASE_ROUTE_MODE:-}"
    require_nonempty "$route_mode" release-route-mode
    create_manifest_dir="${RELEASE_MANIFEST_DIR:-}"
    create_development_sha="${DEVELOPMENT_EVIDENCE_SHA256:-}"
    create_repository="${GITHUB_REPOSITORY:-}"
    require_nonempty "$create_manifest_dir" release-manifest-dir
    require_nonempty "$create_development_sha" development-evidence-sha256
    require_nonempty "$create_repository" github-repository
    python3 "$manifest_helper" create \
      --repository-root "$app_dir" \
      --output-dir "$create_manifest_dir" \
      --workflow-trusted-commit "$workflow_commit" \
      --target-release-commit "$target_commit" \
      --rollback-source-release-commit "$rollback_source_commit" \
      --cli-commit "${CLI_COMMIT:-$target_commit}" \
      --development-evidence-sha256 "$create_development_sha" \
      --control-bundle-sha256 "$control_bundle_sha" \
      --rollback-source-receipt-sha256 "$rollback_source_receipt_sha" \
      --producer-run-id "$GITHUB_RUN_ID" \
      --producer-run-attempt "$GITHUB_RUN_ATTEMPT" \
      --producer-repository "$create_repository" \
      --canary-scope-sha256 "$canary_scope" \
      --route-mode "$route_mode" \
      --target-web-digest "$target_web" \
      --target-core-digest "$target_core" \
      --target-agent-digest "$target_agent" \
      --rollback-web-digest "$rollback_web" \
      --rollback-core-digest "$rollback_core" \
      --rollback-agent-digest "$rollback_agent" \
      --target-manifest-fingerprint "$target_fingerprint" \
      --rollback-manifest-fingerprint "$rollback_fingerprint"
    ;;

  verify-manifest)
    [ -z "$argument" ] || exit 2
    require_source_guard
    require_release_files
    require_manifest_helper
    verify_manifest_dir="${RELEASE_MANIFEST_DIR:-}"
    verify_manifest_sha="${RELEASE_MANIFEST_SHA256:-}"
    require_nonempty "$verify_manifest_dir" release-manifest-dir
    require_nonempty "$verify_manifest_sha" release-manifest-sha256
    python3 "$manifest_helper" verify \
      --repository-root "$app_dir" \
      --manifest-dir "$verify_manifest_dir" \
      --expected-target-commit "$target_commit" \
      --expected-artifact-sha256 "$verify_manifest_sha"
    ;;

  runtime-preflight)
    require_production_approval
    case "$argument" in target|rollback) ;; *) exit 2 ;; esac
    runtime_preflight "$argument"
    printf 'runtime-preflight-ok:%s\n' "$argument"
    ;;

  verify-drain-binding)
    [ -z "$argument" ] || exit 2
    require_release_lock
    require_verified_drain
    printf 'verified-drain-binding-ok:%s\n' "$VERIFIED_DRAIN_SHA256"
    ;;

  transition-runtime-config)
    require_production_approval
    case "$argument" in off|allowlist) ;; *) exit 2 ;; esac
    transition_runtime_config "$argument"
    ;;

  prepare-release)
    [ -z "$argument" ] || exit 2
    require_release_lock
    require_release_files
    verify_manifest
    runtime_group=rollback
    [ "$RELEASE_ACTION" != rollback ] || runtime_group=target
    EXPECTED_RUNTIME_ROUTE_MODE=off runtime_preflight "$runtime_group"
    current_core_config_snapshot off "$(manifest_read canary-scope-sha256)" false >/dev/null
    drain_sha="$(capture_verified_drain)"
    printf 'prepare-release-ok:verifiedDrain:%s\n' "$drain_sha"
    ;;

  consume-live-boundary)
    require_production_approval
    [ -n "$argument" ] || exit 2
    consume_live_boundary "$argument"
    ;;

  mark-live-boundary-applied)
    require_production_approval
    [ -n "$argument" ] || exit 2
    mark_live_boundary_applied "$argument"
    ;;

  boundary-ledger)
    require_production_approval
    [ -z "$argument" ] || exit 2
    build_boundary_ledger
    ;;

  release-database)
    require_release_lock
    require_release_files
    case "$argument" in novelwriter) target_database="$argument" ;;
      novelwriterdev)
        echo "durable-release:error:development-inside-production" >&2
        exit 1
        ;;
      *) exit 2 ;;
    esac
    confirm_file="${DURABLE_AGENT_PRODUCTION_CONFIRM_FILE:-}"
    evidence_dir="${DURABLE_AGENT_PRODUCTION_EVIDENCE_DIR:-}"
    require_nonempty "$confirm_file" production-confirm-file
    require_nonempty "$evidence_dir" production-evidence-dir
    case "$evidence_dir" in
      /*) ;;
      *) echo "durable-release:error:evidence-path" >&2; exit 1 ;;
    esac
    require_route_mode off
    runtime_preflight target
    [ -r "$rollout_gate" ] && [ -r "$migration_helper" ] || exit 1
    state="$(run_migration_helper status "$target_database")"
    case "$state" in
      unmigrated)
        run_rollout_gate pre-contract "$target_database"
        backup_result="$(run_migration_helper backup "$target_database")" || {
          echo "durable-release:error:backup" >&2
          exit 1
        }
        case "$backup_result" in backup-ok:/*) backup_dir="${backup_result#backup-ok:}" ;; *)
          echo "durable-release:error:backup-evidence" >&2
          exit 1
        esac
        attempt=1
        while [ "$attempt" -le 2 ]; do
          APP_DIR="$control_dir" \
          DURABLE_AGENT_MIGRATION_ENV_FILE="$app_dir/.env" \
          DURABLE_AGENT_MIGRATION_BACKUP_ROOT="$app_dir/.durable-agent-execution-backups/$target_database" \
          DURABLE_AGENT_MIGRATION_BACKUP_DIR="$backup_dir" \
          DURABLE_AGENT_MIGRATION_CONFIRM_FILE="$confirm_file" \
          DURABLE_AGENT_BOUNDARY_DRIVER="$control_dir/scripts/durable-agent-v2-release.sh" \
          DURABLE_AGENT_DDL_BOUNDARY="ddl-forward-$attempt" \
            sh "$migration_helper" forward "$target_database"
          run_rollout_gate \
            post-contract-route-off "$target_database"
          attempt=$((attempt + 1))
        done
        transition_runtime_config schema-ready-off
        run_rollout_gate schema-ready-route-off "$target_database"
        run_rollout_gate initialize-drain-indexes "$target_database"
        run_rollout_gate route-off-drain "$target_database"
        ;;
      migrated-empty-v2|migrated-with-v2)
        route_off_gate_for_current_state true
        ;;
      partial) echo "durable-release:error:schema-partial" >&2; exit 1 ;;
      *) echo "durable-release:error:schema-state" >&2; exit 1 ;;
    esac
    if [ -d "$evidence_dir" ]; then
      APP_DIR="$control_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$app_dir/.env" \
        DURABLE_AGENT_CONTRACT_EVIDENCE_DIR="$evidence_dir" \
        sh "$migration_helper" verify-contract "$target_database"
    else
      [ "$state" = "unmigrated" ] || {
        echo "durable-release:error:missing-contract-evidence" >&2
        exit 1
      }
      APP_DIR="$control_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$app_dir/.env" \
        DURABLE_AGENT_CONTRACT_EVIDENCE_DIR="$evidence_dir" \
        sh "$migration_helper" export-contract "$target_database"
      APP_DIR="$control_dir" DURABLE_AGENT_MIGRATION_ENV_FILE="$app_dir/.env" \
        DURABLE_AGENT_CONTRACT_EVIDENCE_DIR="$evidence_dir" \
        sh "$migration_helper" verify-contract "$target_database"
    fi
    printf 'release-database-ok:%s\n' "$target_database"
    ;;

  allowlist-gate)
    [ -z "$argument" ] || exit 2
    require_release_lock
    require_release_files
    require_route_mode allowlist
    runtime_preflight target
    [ -r "$rollout_gate" ] || exit 1
    run_rollout_gate allowlist novelwriter
    printf 'allowlist-gate-ok\n'
    ;;

  rollback-preflight)
    [ -z "$argument" ] || exit 2
    require_release_lock
    require_release_files
    EXPECTED_RUNTIME_ROUTE_MODE=off runtime_preflight target
    [ -r "$rollout_gate" ] && [ -r "$migration_helper" ] || exit 1
    rollback_core="$(manifest_read rollback-core-digest)"
    rollback_agent="$(manifest_read rollback-agent-digest)"
    rollback_fingerprint="$(manifest_read rollback-manifest-fingerprint)"
    require_exact_image "$rollback_core" "$rollback_core"
    require_exact_image "$rollback_agent" "$rollback_agent"
    sh "$image_verifier" core "$rollback_core" >/dev/null || {
      echo "durable-release:error:rollback-core-v1-only" >&2
      exit 1
    }
    sh "$image_verifier" agent "$rollback_agent" "$rollback_fingerprint" >/dev/null || {
      echo "durable-release:error:rollback-agent-incompatible" >&2
      exit 1
    }
    printf 'rollback-preflight-ok\n'
    ;;

  rollback-postflight)
    [ -z "$argument" ] || exit 2
    require_release_lock
    require_release_files
    EXPECTED_RUNTIME_ROUTE_MODE=off runtime_preflight rollback
    [ -r "$rollout_gate" ] || exit 1
    run_rollout_gate route-off-drain novelwriter
    printf 'rollback-postflight-ok\n'
    ;;

  transaction-postflight)
    [ -z "$argument" ] || exit 2
    require_release_lock
    case "$RELEASE_ACTION" in
      route_off_release)
        runtime_preflight target
        route_off_gate_for_current_state false
        ;;
      allowlist_release)
        runtime_preflight target
        run_rollout_gate allowlist novelwriter
        ;;
      rollback)
        EXPECTED_RUNTIME_ROUTE_MODE=off runtime_preflight rollback
        run_rollout_gate route-off-drain novelwriter
        ;;
    esac
    printf 'transaction-postflight-ok:%s\n' "$RELEASE_ACTION"
    ;;

  finalize-allowlist-transaction)
    [ -z "$argument" ] || exit 2
    finalize_allowlist_transaction
    ;;

  transaction-status)
    [ -z "$argument" ] || exit 2
    require_production_approval
    require_control_bundle
    if [ -d "$release_lock_dir" ] && [ -f "$release_lock_file" ]; then
      require_release_lock
      printf 'release-transaction-status:%s\n' "$(receipt_commit_status)"
    else
      current="$(current_receipt_sha)"
      [ "$(receipt_read "$current" lock-id)" = "$release_lock_id" ] \
        && [ "$(receipt_read "$current" run-id)" = "$GITHUB_RUN_ID" ] \
        && [ "$(receipt_read "$current" run-attempt)" = "$GITHUB_RUN_ATTEMPT" ] \
        && [ "$(receipt_read "$current" release-action)" = "$RELEASE_ACTION" ] \
        && [ "$(receipt_read "$current" manifest-sha256)" = \
          "$RELEASE_MANIFEST_SHA256" ] \
        && [ "$(receipt_read "$current" control-bundle-sha256)" = \
          "$control_bundle_sha" ] || {
          echo "durable-release:error:transaction-status-owner" >&2
          exit 1
        }
      printf 'release-transaction-status:finalized\n'
    fi
    ;;

  reconcile-transaction)
    [ -z "$argument" ] || exit 2
    require_release_lock
    reconcile_transaction_internal
    ;;

  commit-transaction)
    [ -z "$argument" ] || exit 2
    require_release_lock
    [ "$RELEASE_ACTION" != allowlist_release ] || {
      echo "durable-release:error:allowlist-requires-single-finalizer" >&2
      exit 1
    }
    prepare_release_receipt >/dev/null
    commit_prepared_receipt >/dev/null
    finalize_committed_transaction
    ;;

  mark-transaction-failed)
    [ -z "$argument" ] || exit 2
    if [ ! -d "$release_lock_dir" ] && [ ! -e "$release_lock_file" ]; then
      current="$(current_receipt_sha)"
      [ "$(receipt_read "$current" lock-id)" = "$release_lock_id" ] \
        && [ "$(receipt_read "$current" run-id)" = "$GITHUB_RUN_ID" ] \
        && [ "$(receipt_read "$current" run-attempt)" = "$GITHUB_RUN_ATTEMPT" ] \
        && [ "$(receipt_read "$current" release-action)" = "$RELEASE_ACTION" ] \
        && [ "$(receipt_read "$current" manifest-sha256)" = \
          "$RELEASE_MANIFEST_SHA256" ] || exit 1
      printf 'release-transaction-already-committed:%s\n' "$release_lock_id"
      exit 0
    fi
    if [ -f "$release_lock_state" ] && [ ! -L "$release_lock_state" ] \
      && [ "$(cat "$release_lock_state")" = failed ]; then
      require_failed_release_lock
      # 内容不变；仅补齐 replace 后可能未完成的 state/父目录 fsync。
      write_lock_state failed
      printf 'release-transaction-failed:%s\n' "$release_lock_id"
      exit 0
    fi
    require_release_lock
    compensation_status=0
    mark_settled_compensation_failed || compensation_status=$?
    case "$compensation_status" in
      0)
        printf 'release-transaction-failed:%s\n' "$release_lock_id"
        exit 0
        ;;
      2) ;;
      *)
        echo "durable-release:error:settled-compensation-invalid" >&2
        exit 1
        ;;
    esac
    reconcile_status=0
    reconcile_transaction_internal || reconcile_status=$?
    if [ "$reconcile_status" -eq 0 ]; then
      printf 'release-transaction-already-committed:%s\n' "$release_lock_id"
      exit 0
    fi
    if [ -f "$release_lock_state" ] && [ ! -L "$release_lock_state" ] \
      && [ "$(cat "$release_lock_state")" = failed ] \
      && (require_failed_release_lock); then
      if write_lock_state failed; then
        printf 'release-transaction-failed:%s\n' "$release_lock_id"
        exit 0
      fi
    fi
    echo "durable-release:error:transaction-outcome-unknown" >&2
    exit 1
    ;;

  cleanup-failed-transaction)
    [ -z "$argument" ] || exit 2
    require_production_approval
    require_control_bundle
    require_sha256 "$release_lock_id" release-lock-id
    owner_run_id="${RELEASE_LOCK_OWNER_RUN_ID:-}"
    owner_run_attempt="${RELEASE_LOCK_OWNER_RUN_ATTEMPT:-}"
    owner_operation="${RELEASE_LOCK_OWNER_ACTION:-}"
    owner_workflow_commit="${RELEASE_LOCK_OWNER_WORKFLOW_COMMIT:-}"
    owner_target_commit="${RELEASE_LOCK_OWNER_TARGET_COMMIT:-}"
    owner_control_bundle_sha="${RELEASE_LOCK_OWNER_CONTROL_BUNDLE_SHA256:-}"
    require_nonempty "$owner_run_id" owner-run-id
    require_nonempty "$owner_run_attempt" owner-run-attempt
    require_nonempty "$owner_operation" owner-action
    require_nonempty "$owner_workflow_commit" owner-workflow-commit
    require_nonempty "$owner_target_commit" owner-target-commit
    require_nonempty "$owner_control_bundle_sha" owner-control-bundle-sha
    require_positive_decimal "$owner_run_id" owner-run-id
    require_positive_decimal "$owner_run_attempt" owner-run-attempt
    validate_release_action "$owner_operation"
    require_commit "$owner_workflow_commit" owner-workflow-commit
    require_commit "$owner_target_commit" owner-target-commit
    require_sha256 "$owner_control_bundle_sha" owner-control-bundle-sha
    [ "${INKFORGE_RELEASE_CLEANUP_CONFIRM:-}" = \
      "cleanup-failed-release:$release_lock_id" ] || {
        echo "durable-release:error:cleanup-confirm" >&2
        exit 1
      }
    owner_evidence=0
    if [ -e "$release_lock_file" ] || [ -L "$release_lock_file" ]; then
      [ -f "$release_lock_file" ] && [ ! -L "$release_lock_file" ] || {
        echo "durable-release:error:cleanup-fixed-lock" >&2
        exit 1
      }
      verify_lock_owner "$release_lock_file" "$owner_run_id" "$owner_run_attempt" \
        "$owner_operation" "$owner_workflow_commit" "$owner_target_commit" \
        "$owner_control_bundle_sha" || {
          echo "durable-release:error:cleanup-owner" >&2
          exit 1
        }
      owner_evidence=1
    fi
    if [ -e "$release_lock_partial_owner" ] || [ -L "$release_lock_partial_owner" ]; then
      verify_lock_owner "$release_lock_partial_owner" "$owner_run_id" \
        "$owner_run_attempt" "$owner_operation" "$owner_workflow_commit" \
        "$owner_target_commit" "$owner_control_bundle_sha" || exit 1
      if [ -e "$release_lock_file" ]; then
        [ "$release_lock_partial_owner" -ef "$release_lock_file" ] || {
          echo "durable-release:error:cleanup-owner-inode" >&2
          exit 1
        }
      fi
      owner_evidence=1
    fi
    if [ -L "$release_lock_dir" ] \
      || { [ -e "$release_lock_dir" ] && [ ! -d "$release_lock_dir" ]; }; then
      echo "durable-release:error:cleanup-state-dir" >&2
      exit 1
    fi
    if [ -d "$release_lock_dir" ]; then
      [ ! -L "$release_lock_dir" ] && [ "$(private_mode "$release_lock_dir")" = 700 ] \
        || exit 1
      if [ -e "$release_lock_owner" ]; then
        verify_lock_owner "$release_lock_owner" "$owner_run_id" \
          "$owner_run_attempt" "$owner_operation" "$owner_workflow_commit" \
          "$owner_target_commit" "$owner_control_bundle_sha" || exit 1
        if [ -e "$release_lock_file" ]; then
          [ "$release_lock_owner" -ef "$release_lock_file" ] || {
            echo "durable-release:error:cleanup-owner-inode" >&2
            exit 1
          }
        fi
        owner_evidence=1
      fi
      if [ -e "$release_lock_state" ] || [ -L "$release_lock_state" ]; then
        [ -f "$release_lock_state" ] && [ ! -L "$release_lock_state" ] \
          && [ "$(private_mode "$release_lock_state")" = 600 ] || exit 1
        case "$(cat "$release_lock_state")" in active|failed) ;; *) exit 1 ;; esac
      fi
    fi
    [ "$owner_evidence" -eq 1 ] || {
      echo "durable-release:error:cleanup-owner-evidence" >&2
      exit 1
    }
    cleanup_owner_path=""
    for candidate in "$release_lock_owner" "$release_lock_file" \
      "$release_lock_partial_owner"
    do
      if [ -f "$candidate" ] && [ ! -L "$candidate" ]; then
        cleanup_owner_path="$candidate"
        break
      fi
    done
    [ -n "$cleanup_owner_path" ] || exit 1
    cleanup_owner_sha="$(sha256sum "$cleanup_owner_path" | cut -d ' ' -f 1)"
    require_sha256 "$cleanup_owner_sha" cleanup-owner-sha256
    if [ -d "$release_lock_dir" ]; then
      python3 - "$release_lock_dir" "$cleanup_owner_sha" <<'PY'
import re
import stat
import sys
from pathlib import Path

directory = Path(sys.argv[1])
owner_sha = sys.argv[2]
allowed_files = {
    ".current-receipt.partial",
    ".current-receipt.restore.partial",
    ".boundary-ledger.partial",
    ".boundary-live-allowlist-config.partial",
    ".boundary-live-compose-release.partial",
    ".boundary-live-compose-rollback.partial",
    ".boundary-live-ddl-forward-1.partial",
    ".boundary-live-ddl-forward-2.partial",
    ".env.restore.partial",
    ".env.transition.partial",
    "allowlist-lease-id",
    "base-receipt.sha256",
    "boundary-ledger.json",
    "env.before",
    "env.before.sha256",
    "env.allowlist.before",
    "env.allowlist.before.sha256",
    "expected-receipt.sha256",
    "owner",
    "receipt-commit-confirmed",
    "receipt-current-unfsynced",
    "receipt-intent.json",
    "runtime-config-transition",
    "state",
    "verified-drain-report.json",
    "verified-drain.json",
}
allowed_directories = {
    ".release-receipt-candidate.partial",
    "boundary-evidence",
    "release-receipt-candidate",
    "token-usage-control",
}
children = {path.name: path for path in directory.iterdir()}
state_partials = [
    name
    for name in children
    if name.startswith(".state") and name.endswith(".partial")
]
if len(state_partials) > 1:
    raise SystemExit("lock-state-multiple-partials")
if state_partials:
    name = state_partials[0]
    match = re.fullmatch(
        r"\.state-([0-9a-f]{64})-(active|prepared|committed_cleanup_pending|failed)\.partial",
        name,
    )
    if match is None or match.group(1) != owner_sha:
        raise SystemExit("lock-state-foreign-partial")
    partial = children[name]
    if (
        partial.is_symlink()
        or not partial.is_file()
        or stat.S_IMODE(partial.stat().st_mode) != 0o600
        or partial.read_bytes() != f"{match.group(2)}\n".encode("ascii")
    ):
        raise SystemExit("lock-state-partial")
    allowed_files.add(name)
if set(children) - allowed_files - allowed_directories:
    raise SystemExit("lock-directory-extra-files")
for name, path in children.items():
    if path.is_symlink():
        raise SystemExit("lock-directory-symlink")
    if name in allowed_files:
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SystemExit("lock-directory-file")
        continue
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SystemExit("lock-directory-subdirectory")
    if name in {"release-receipt-candidate", ".release-receipt-candidate.partial"}:
        expected = {"release-receipt.json", "SHA256SUMS"}
        nested = {item.name: item for item in path.iterdir()}
        if set(nested) - expected:
            raise SystemExit("receipt-candidate-extra-files")
        for item in nested.values():
            if item.is_symlink() or not item.is_file() or stat.S_IMODE(item.stat().st_mode) & 0o077:
                raise SystemExit("receipt-candidate-file")
        continue
    if name == "boundary-evidence":
        for item in path.iterdir():
            if item.is_symlink() or not item.is_file() or stat.S_IMODE(item.stat().st_mode) & 0o077:
                raise SystemExit("boundary-evidence-file")
        continue
    expected = {
        "scripts/token-usage-production-migration.sh",
        "scripts/migrations/20260823_token_usage_details.production.sql",
        "scripts/migrations/rollback_20260823_token_usage_details.sql",
        ".env",
    }
    actual = set()
    for item in path.rglob("*"):
        if item.is_symlink():
            raise SystemExit("token-control-symlink")
        if item.is_file():
            if stat.S_IMODE(item.stat().st_mode) & 0o077:
                raise SystemExit("token-control-file-mode")
            actual.add(item.relative_to(path).as_posix())
        elif not item.is_dir() or stat.S_IMODE(item.stat().st_mode) & 0o077:
            raise SystemExit("token-control-entry")
    if actual - expected:
        raise SystemExit("token-control-extra-files")
PY
      for candidate in \
        "$release_lock_dir/release-receipt-candidate" \
        "$release_lock_dir/.release-receipt-candidate.partial"
      do
        if [ -d "$candidate" ]; then
          rm -f -- "$candidate/release-receipt.json" "$candidate/SHA256SUMS"
          rmdir "$candidate"
        fi
      done
      token_control="$release_lock_dir/token-usage-control"
      if [ -d "$token_control" ]; then
        rm -f -- "$token_control/.env" \
          "$token_control/scripts/token-usage-production-migration.sh" \
          "$token_control/scripts/migrations/20260823_token_usage_details.production.sql" \
          "$token_control/scripts/migrations/rollback_20260823_token_usage_details.sql"
        [ ! -d "$token_control/scripts/migrations" ] \
          || rmdir "$token_control/scripts/migrations"
        [ ! -d "$token_control/scripts" ] || rmdir "$token_control/scripts"
        rmdir "$token_control"
      fi
      if [ -d "$boundary_evidence_dir" ]; then
        for path in "$boundary_evidence_dir"/*; do
          [ ! -e "$path" ] || rm -f -- "$path"
        done
        rmdir "$boundary_evidence_dir"
      fi
      for path in "$release_lock_dir"/.state-*.partial; do
        [ ! -e "$path" ] || rm -f -- "$path"
      done
      for path in \
        "$release_lock_dir/.current-receipt.partial" \
        "$release_lock_dir/.current-receipt.restore.partial" \
        "$release_lock_dir/.boundary-ledger.partial" \
        "$release_lock_dir/.boundary-live-allowlist-config.partial" \
        "$release_lock_dir/.boundary-live-compose-release.partial" \
        "$release_lock_dir/.boundary-live-compose-rollback.partial" \
        "$release_lock_dir/.boundary-live-ddl-forward-1.partial" \
        "$release_lock_dir/.boundary-live-ddl-forward-2.partial" \
        "$release_lock_dir/.env.restore.partial" \
        "$release_lock_dir/.env.transition.partial" \
        "$release_lock_dir/allowlist-lease-id" \
        "$release_lock_dir/base-receipt.sha256" \
        "$release_lock_dir/boundary-ledger.json" \
        "$release_lock_dir/env.before" "$release_lock_dir/env.before.sha256" \
        "$release_lock_dir/env.allowlist.before" \
        "$release_lock_dir/env.allowlist.before.sha256" \
        "$release_lock_dir/expected-receipt.sha256" \
        "$release_lock_dir/receipt-commit-confirmed" \
        "$release_lock_dir/receipt-current-unfsynced" \
        "$release_lock_dir/receipt-intent.json" \
        "$release_lock_dir/runtime-config-transition" \
        "$(verified_drain_path)" "$(verified_drain_report_path)" \
        "$release_lock_state" "$release_lock_owner"
      do
        [ ! -e "$path" ] || rm -f -- "$path"
      done
      rmdir "$release_lock_dir"
    fi
    [ ! -e "$release_lock_partial_owner" ] || rm -f -- "$release_lock_partial_owner"
    rm -f -- "$release_lock_file"
    printf 'release-transaction-cleaned:%s\n' "$release_lock_id"
    ;;
esac
