"""Tests for the parts of cloudflare_deploy.py that don't touch a real
Cloudflare account: config-file generation/idempotency and output parsing.
Nothing here calls `wrangler login`/`deploy`/etc. or makes network requests.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cloudflare_deploy as cd


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    cloudflare_dir = tmp_path / "cloudflare"
    cloudflare_dir.mkdir()
    monkeypatch.setattr(cd, "APP_DIR", tmp_path)
    monkeypatch.setattr(cd, "CLOUDFLARE_DIR", cloudflare_dir)
    monkeypatch.setattr(cd, "WRANGLER_TOML", cloudflare_dir / "wrangler.toml")
    return cloudflare_dir


def test_write_wrangler_toml_fresh(isolated):
    cd.write_wrangler_toml()
    text = cd.WRANGLER_TOML.read_text(encoding="utf-8")
    assert 'name = "knowledge-vault-inbox"' in text
    assert 'main = "worker.js"' in text
    assert "[[kv_namespaces]]" not in text  # not provisioned yet


def test_write_wrangler_toml_preserves_kv_block(isolated):
    cd.write_wrangler_toml()
    with cd.WRANGLER_TOML.open("a", encoding="utf-8") as f:
        f.write('\n[[kv_namespaces]]\nbinding = "INBOX"\nid = "deadbeefdeadbeefdeadbeefdeadbeef"\n')
    before = cd.WRANGLER_TOML.read_text(encoding="utf-8")
    cd.write_wrangler_toml()
    after = cd.WRANGLER_TOML.read_text(encoding="utf-8")
    assert "deadbeefdeadbeefdeadbeefdeadbeef" in after
    assert after.count("[[kv_namespaces]]") == 1


def test_write_wrangler_toml_stable_across_reruns(isolated):
    cd.write_wrangler_toml()
    with cd.WRANGLER_TOML.open("a", encoding="utf-8") as f:
        f.write('\n[[kv_namespaces]]\nbinding = "INBOX"\nid = "deadbeefdeadbeefdeadbeefdeadbeef"\n')
    first = cd.WRANGLER_TOML.read_text(encoding="utf-8")
    cd.write_wrangler_toml()
    cd.write_wrangler_toml()
    third = cd.WRANGLER_TOML.read_text(encoding="utf-8")
    assert first == third  # no accumulating blank lines / duplication


def test_find_existing_kv_id_matches_manual_dashboard_naming(monkeypatch):
    import json as json_mod

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = json_mod.dumps([
            {"id": "11111111111111111111111111111111", "title": "INBOX"},
            {"id": "22222222222222222222222222222222", "title": "unrelated"},
        ])

    monkeypatch.setattr(cd, "_npx", lambda *a, **k: FakeResult())
    assert cd.find_existing_kv_id() == "11111111111111111111111111111111"


def test_find_existing_kv_id_matches_cli_style_naming(monkeypatch):
    import json as json_mod

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = json_mod.dumps([{"id": "33333333333333333333333333333333",
                                  "title": "knowledge-vault-inbox-INBOX"}])

    monkeypatch.setattr(cd, "_npx", lambda *a, **k: FakeResult())
    assert cd.find_existing_kv_id() == "33333333333333333333333333333333"


def test_find_existing_kv_id_none_when_no_match(monkeypatch):
    import json as json_mod

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = json_mod.dumps([{"id": "x", "title": "unrelated"}])

    monkeypatch.setattr(cd, "_npx", lambda *a, **k: FakeResult())
    assert cd.find_existing_kv_id() is None


def test_ensure_kv_namespace_reuses_existing_before_creating(isolated, monkeypatch):
    cd.write_wrangler_toml()
    monkeypatch.setattr(cd, "find_existing_kv_id", lambda: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    create_calls = []
    monkeypatch.setattr(cd, "_npx", lambda *a, **k: create_calls.append(a))
    cd.ensure_kv_namespace()
    assert create_calls == []  # never tried to create — reused instead
    text = cd.WRANGLER_TOML.read_text(encoding="utf-8")
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in text


def test_ensure_kv_namespace_skips_when_already_bound(isolated, monkeypatch):
    cd.write_wrangler_toml()
    with cd.WRANGLER_TOML.open("a", encoding="utf-8") as f:
        f.write('\n[[kv_namespaces]]\nbinding = "INBOX"\nid = "deadbeefdeadbeefdeadbeefdeadbeef"\n')
    calls = []
    monkeypatch.setattr(cd, "_npx", lambda *a, **k: calls.append((a, k)))
    cd.ensure_kv_namespace()
    assert calls == []  # never shelled out — already provisioned


def test_url_regex_matches_deploy_output():
    stdout = (
        "Uploaded knowledge-vault-inbox (2.10 sec)\n"
        "Deployed knowledge-vault-inbox triggers (0.45 sec)\n"
        "  https://knowledge-vault-inbox.janedoe.workers.dev\n"
        "Current Version ID: abc123\n"
    )
    m = cd.URL_RE.search(stdout)
    assert m and m.group(0) == "https://knowledge-vault-inbox.janedoe.workers.dev"


def test_kv_id_regex_matches_create_output():
    stdout = (
        'Add the following to your configuration file:\n'
        '[[kv_namespaces]]\n'
        'binding = "INBOX"\n'
        'id = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"\n'
    )
    m = cd.KV_ID_RE.search(stdout)
    assert m and m.group(1) == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


def test_already_logged_in_false_when_not_authenticated(monkeypatch):
    class FakeResult:
        returncode = 0
        stdout = "You are not authenticated. Please run `wrangler login`."
        stderr = ""

    monkeypatch.setattr(cd, "_npx", lambda *a, **k: FakeResult())
    assert cd.already_logged_in() is False


def test_already_logged_in_true_when_authenticated(monkeypatch):
    class FakeResult:
        returncode = 0
        stdout = "You are logged in with an OAuth Token, associated with the email j@example.com."
        stderr = ""

    monkeypatch.setattr(cd, "_npx", lambda *a, **k: FakeResult())
    assert cd.already_logged_in() is True


def _mock_steps(monkeypatch, calls, node_ok=True, logged_in=False):
    monkeypatch.setattr(cd, "ensure_node", lambda: calls.append("ensure_node") or node_ok)
    monkeypatch.setattr(cd, "already_logged_in", lambda: calls.append("already_logged_in") or logged_in)
    monkeypatch.setattr(cd, "login", lambda: calls.append("login"))
    monkeypatch.setattr(cd, "write_wrangler_toml", lambda: calls.append("write_wrangler_toml"))
    monkeypatch.setattr(cd, "ensure_kv_namespace", lambda: calls.append("ensure_kv_namespace"))
    monkeypatch.setattr(cd, "set_token_secret", lambda token: calls.append(f"set_token_secret({token})"))
    monkeypatch.setattr(cd, "deploy", lambda: calls.append("deploy") or "https://fake.workers.dev")


def test_run_calls_steps_in_order(monkeypatch):
    calls = []
    _mock_steps(monkeypatch, calls, logged_in=False)
    url = cd.run("mytoken")
    assert calls == ["ensure_node", "already_logged_in", "login", "write_wrangler_toml",
                     "ensure_kv_namespace", "set_token_secret(mytoken)", "deploy"]
    assert url == "https://fake.workers.dev"


def test_run_skips_login_when_already_authenticated(monkeypatch):
    calls = []
    _mock_steps(monkeypatch, calls, logged_in=True)
    cd.run("mytoken")
    assert "login" not in calls


def test_run_raises_and_stops_early_if_node_install_fails(monkeypatch):
    calls = []
    _mock_steps(monkeypatch, calls, node_ok=False)
    with pytest.raises(cd.DeployError):
        cd.run("mytoken")
    assert calls == ["ensure_node"]  # nothing else attempted
