import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "infra" / "compose.yaml"
ENV_EXAMPLE = ROOT / ".env.example"
HTTP_BOOTSTRAP = ROOT / "infra" / "host-nginx" / "inkforge-http-bootstrap.conf"
HTTPS_CONFIG = ROOT / "infra" / "host-nginx" / "inkforge.conf"
CERTBOT_HOOK = ROOT / "infra" / "certbot" / "reload-nginx.sh"


def _server_blocks(source: str) -> list[str]:
    blocks: list[str] = []
    for match in re.finditer(r"(?m)^\s*server\s*\{", source):
        depth = 0
        for index in range(match.start(), len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(source[match.start() : index + 1])
                    break
    return blocks


def _server_by_exact_name(source: str, name: str) -> str:
    pattern = re.compile(rf"(?m)^\s*server_name\s+{re.escape(name)};\s*$")
    for block in _server_blocks(source):
        if pattern.search(block):
            return block
    raise AssertionError(f"缺少 server_name {name} 的服务块")


def _assert_internal_routes_are_blocked(source: str) -> None:
    assert re.search(r"location\s+=\s+/internal\s*\{\s*return\s+404;", source)
    assert re.search(r"location\s+\^~\s+/internal/\s*\{\s*return\s+404;", source)


def _assert_reverse_proxy_contract(source: str, proto: str) -> None:
    assert "proxy_pass http://127.0.0.1:43120;" in source
    assert "proxy_set_header Host $host;" in source
    assert "proxy_set_header X-Real-IP $remote_addr;" in source
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in source
    assert f"proxy_set_header X-Forwarded-Proto {proto};" in source
    assert "proxy_buffering off;" in source
    assert "proxy_cache off;" in source
    assert "proxy_read_timeout 3600s;" in source
    assert "proxy_send_timeout 3600s;" in source
    assert "client_max_body_size 50m;" in source


def _assert_certbot_tls_contract(source: str) -> None:
    assert "ssl_certificate /etc/letsencrypt/live/inkforge.cn/fullchain.pem;" in source
    assert "ssl_certificate_key /etc/letsencrypt/live/inkforge.cn/privkey.pem;" in source
    assert "include /etc/letsencrypt/options-ssl-nginx.conf;" in source
    assert "ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;" in source


def test_http_bootstrap_preserves_acme_and_existing_http_service() -> None:
    source = HTTP_BOOTSTRAP.read_text(encoding="utf-8")
    blocks = _server_blocks(source)

    assert len(blocks) == 1
    server = blocks[0]
    assert re.search(r"listen\s+80\s+default_server;", server)
    assert "server_name inkforge.cn www.inkforge.cn;" in server
    assert "location ^~ /.well-known/acme-challenge/" in server
    assert "root /var/www/letsencrypt;" in server
    assert "try_files $uri =404;" in server
    _assert_internal_routes_are_blocked(server)
    _assert_reverse_proxy_contract(server, "http")
    assert "ssl_certificate" not in server
    assert "return 308" not in server


def test_final_https_config_redirects_to_root_domain_and_terminates_tls() -> None:
    source = HTTPS_CONFIG.read_text(encoding="utf-8")
    blocks = _server_blocks(source)

    http = next(block for block in blocks if re.search(r"listen\s+80\s+default_server;", block))
    root_https = _server_by_exact_name(source, "inkforge.cn")
    www_https = _server_by_exact_name(source, "www.inkforge.cn")

    assert "location ^~ /.well-known/acme-challenge/" in http
    assert "root /var/www/letsencrypt;" in http
    assert "try_files $uri =404;" in http
    _assert_internal_routes_are_blocked(http)
    assert "return 308 https://inkforge.cn$request_uri;" in http

    for server in (root_https, www_https):
        assert re.search(r"listen\s+443\s+ssl;", server)
        _assert_certbot_tls_contract(server)

    assert "return 308 https://inkforge.cn$request_uri;" in www_https
    assert "proxy_pass" not in www_https

    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in root_https
    assert "includesubdomains" not in source.lower()
    assert "preload" not in source.lower()
    _assert_internal_routes_are_blocked(root_https)
    _assert_reverse_proxy_contract(root_https, "https")


def test_certbot_deploy_hook_only_validates_and_reloads_nginx() -> None:
    lines = CERTBOT_HOOK.read_text(encoding="utf-8").splitlines()

    assert lines == [
        "#!/bin/sh",
        "set -eu",
        "nginx -t",
        "systemctl reload nginx",
    ]


def test_certbot_deploy_hook_is_tracked_as_executable() -> None:
    git = shutil.which("git")
    assert git is not None
    tracked_path = CERTBOT_HOOK.relative_to(ROOT).as_posix()
    completed = subprocess.run(  # noqa: S603
        [git, "ls-files", "--stage", "--", tracked_path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.split(maxsplit=1)[0] == "100755"


def test_production_proxy_port_contract_stays_consistent() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert '"127.0.0.1:${INKFORGE_PORT:-43120}:8080"' in compose
    assert "INKFORGE_PORT=43120" in env_example
    assert "生产部署必须保持 INKFORGE_PORT=43120" in env_example
    for path in (HTTP_BOOTSTRAP, HTTPS_CONFIG):
        source = path.read_text(encoding="utf-8")
        assert source.count("proxy_pass http://127.0.0.1:43120;") == 1


def test_https_templates_do_not_embed_secret_material() -> None:
    for path in (HTTP_BOOTSTRAP, HTTPS_CONFIG, CERTBOT_HOOK):
        source = path.read_text(encoding="utf-8")
        assert "-----BEGIN" not in source
        assert "PRIVATE KEY-----" not in source
