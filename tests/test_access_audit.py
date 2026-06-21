"""Tests for scripts/audit_source_access.py — the reachability auditor that
corrects the ``access`` flag from measured results.

All offline: ``httpx.Client`` is faked, and the in-place rewrite is exercised on
a temp copy of config/sources.py so the real config is never touched.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit_source_access.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("audit_source_access", AUDIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    # register before exec so dataclasses can resolve the module for `int | None`
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


audit = _load_audit()


class _Resp:
    def __init__(self, status, headers=None, url="https://example.test/"):
        self.status_code = status
        self.headers = headers or {}
        self.url = url
        self.is_success = 200 <= status < 300


def _patch_client(monkeypatch, resp):
    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return resp

    monkeypatch.setattr("httpx.Client", _Client)


# --- classify() distinguishes environment block from real origin response ---

def test_classify_open(monkeypatch):
    _patch_client(monkeypatch, _Resp(200, url="https://misa.gov.sa/en"))
    cls, status, _ = audit.classify("https://misa.gov.sa/en", audit.ScrapeConfig())
    assert cls == "open" and status == 200
    assert audit.suggest(cls) == "open"


def test_classify_egress_denied_is_inconclusive(monkeypatch):
    # the managed proxy denies the host — about our env, not the site
    _patch_client(monkeypatch, _Resp(403, headers={"x-deny-reason": "host_not_allowed"}))
    cls, _, _ = audit.classify("https://neom.com", audit.ScrapeConfig())
    assert cls == "egress_denied"
    assert audit.suggest(cls) is None          # never triggers a rewrite


def test_classify_origin_block(monkeypatch):
    _patch_client(monkeypatch, _Resp(451))
    cls, _, _ = audit.classify("https://x.test", audit.ScrapeConfig())
    assert cls == "blocked"
    assert audit.suggest(cls) == "saudi_ip"


def test_classify_login_redirect(monkeypatch):
    _patch_client(monkeypatch, _Resp(200, url="https://absher.sa/login"))
    cls, _, _ = audit.classify("https://absher.sa", audit.ScrapeConfig())
    assert cls == "login"
    assert audit.suggest(cls) == "saudi_ip"


def test_classify_network_error(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            raise RuntimeError("conn reset")

    monkeypatch.setattr("httpx.Client", _Boom)
    cls, status, _ = audit.classify("https://x.test", audit.ScrapeConfig())
    assert cls == "error" and status is None
    assert audit.suggest(cls) is None


# --- plan_changes() applies the conservative rules -------------------------

def _probe(ns, current, cls):
    return audit.Probe(ns, "https://x.test", current, cls, 200, "", audit.suggest(cls))


def test_proven_open_downgrade_applies():
    probes = [_probe("misa", "saudi_ip", "open")]
    assert audit.plan_changes(probes, apply_blocks=False) == {"misa": "open"}


def test_egress_denied_changes_nothing():
    probes = [_probe("misa", "saudi_ip", "egress_denied")]
    assert audit.plan_changes(probes, apply_blocks=False) == {}


def test_open_to_block_requires_optin():
    probes = [_probe("neom", "open", "blocked")]
    assert audit.plan_changes(probes, apply_blocks=False) == {}   # risky: not by default
    assert audit.plan_changes(probes, apply_blocks=True) == {"neom": "saudi_ip"}


# --- rewrite_sources_py() edits only the target row, in place --------------

def test_rewrite_targets_only_the_named_row(monkeypatch, tmp_path):
    tmp = tmp_path / "sources.py"
    tmp.write_text((REPO_ROOT / "config" / "sources.py").read_text(encoding="utf-8"),
                   encoding="utf-8")
    monkeypatch.setattr(audit, "SOURCES_PY", tmp)

    applied = audit.rewrite_sources_py({"misa": "open"})
    assert applied == ["misa"]

    out = tmp.read_text(encoding="utf-8").splitlines()
    misa_line = next(l for l in out if l.lstrip().startswith('("misa",'))
    assert '"open"' in misa_line and '"saudi_ip"' not in misa_line
    assert '"https://misa.gov.sa/en"' in misa_line        # URL preserved
    # an unrelated saudi_ip row is left untouched
    monshaat_line = next(l for l in out if l.lstrip().startswith('("monshaat",'))
    assert '"saudi_ip"' in monshaat_line
