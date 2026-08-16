"""Tests for sandbox isolation of the differential run.

Docker is not assumed to be installed — and deliberately is never invoked here.
What these lock down is the part that must hold whether or not a daemon is
running: that the hardening flags are actually passed, that mounts are
read-only, and above all that requiring isolation and not getting it means
*nothing executes*. A sandbox that quietly degrades to host execution is the
exact failure this module exists to prevent, so that path is tested by asserting
the host runner is never reached.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from codeshift import config
from codeshift.adapters.python import runner as py_runner
from codeshift.adapters.typescript import runner as ts_runner
from codeshift.sandbox import docker_runner, policy
from codeshift.sandbox.docker_runner import EXIT_UNAVAILABLE, Mount

FIXTURE = str(Path(__file__).resolve().parents[1] / "fixtures" / "sample_app")


@pytest.fixture(autouse=True)
def _clean_policy():
    """`effective()` caches so its warning is logged once per run, not per call."""
    policy.reset()
    yield
    policy.reset()


def _configure(monkeypatch, **kwargs):
    monkeypatch.setattr(config, "settings", replace(config.settings, **kwargs))


def _no_docker(monkeypatch):
    monkeypatch.setattr(docker_runner, "docker_available", lambda: False)


# --- the hardening is real ---

def test_container_argv_carries_every_hardening_flag():
    argv = docker_runner.container_argv(
        "img:1", ["python", "x.py"], mounts=[Mount(host=FIXTURE, container="/work")]
    )
    joined = " ".join(argv)
    for flag in ("--network none", "--read-only", "--user 1000:1000",
                 "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit 128", "--memory 512m", "--cpus 1"):
        assert flag in joined, f"missing {flag}"
    assert "--rm" in argv and "-i" in argv          # -i: the driver reads stdin
    assert argv[-2:] == ["python", "x.py"]          # image precedes the command
    assert "img:1" in argv


def test_mounts_are_read_only():
    argv = docker_runner.container_argv(
        "img:1", ["true"],
        mounts=[Mount(host=FIXTURE, container="/work"), Mount(host=FIXTURE, container="/driver")],
    )
    volumes = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert len(volumes) == 2
    assert all(v.endswith(":ro") for v in volumes)
    assert all(":/work:ro" in v or ":/driver:ro" in v for v in volumes)


def test_mount_arg_uses_posix_path_for_docker_desktop():
    arg = Mount(host=FIXTURE, container="/work").as_arg()
    assert "\\" not in arg
    assert arg.endswith(":/work:ro")


def test_image_tag_is_content_addressed():
    """A hand-edited Dockerfile must not reuse the previous image."""
    tag = docker_runner.image_tag("python")
    assert tag.startswith("codeshift-sandbox-python:")
    assert len(tag.split(":")[1]) == 12
    assert docker_runner.image_tag("node") != tag


def test_staged_driver_directory_holds_only_the_driver():
    """The drivers sit beside CodeShift's own modules; only the driver travels."""
    staged = Path(docker_runner.stage_driver(py_runner._DRIVER))
    assert [p.name for p in staged.iterdir()] == ["_driver.py"]


def test_run_in_container_reports_unavailable_without_docker(monkeypatch):
    monkeypatch.setattr(docker_runner, "_docker", lambda: None)
    result = docker_runner.run_in_container("python", ["true"], mounts=[])
    assert result.exit_code == EXIT_UNAVAILABLE


# --- the policy resolves honestly ---

def test_docker_mode_without_docker_is_unavailable_not_host(monkeypatch):
    _configure(monkeypatch, sandbox="docker")
    _no_docker(monkeypatch)
    assert policy.effective() == "unavailable"


def test_auto_mode_falls_back_to_host_when_docker_is_missing(monkeypatch):
    _configure(monkeypatch, sandbox="auto")
    _no_docker(monkeypatch)
    assert policy.effective() == "host"


def test_auto_mode_prefers_docker_when_available(monkeypatch):
    _configure(monkeypatch, sandbox="auto")
    monkeypatch.setattr(docker_runner, "docker_available", lambda: True)
    assert policy.effective() == "docker"


def test_host_mode_never_probes_docker(monkeypatch):
    def _boom():
        raise AssertionError("host mode must not consult Docker")

    _configure(monkeypatch, sandbox="host")
    monkeypatch.setattr(docker_runner, "docker_available", _boom)
    assert policy.effective() == "host"


def test_describe_names_the_host_path_as_unisolated():
    assert "without isolation" in policy.describe("host")
    assert "no network" in policy.describe("docker")


# --- required isolation refuses to execute ---

def test_python_runner_does_not_execute_when_isolation_is_required_and_absent(monkeypatch):
    _configure(monkeypatch, sandbox="docker")
    _no_docker(monkeypatch)

    def _never(*args, **kwargs):
        raise AssertionError("code must not run on the host when Docker was required")

    monkeypatch.setattr(py_runner, "_run_host", _never)
    monkeypatch.setattr(py_runner, "_run_docker", _never)

    outs = py_runner.run_functions(FIXTURE, "models", "make_user", [[1, "Ada"], [2, "Bo"]])
    assert len(outs) == 2
    assert all((not o.ok) and o.error == "sandbox_unavailable" for o in outs)


def test_typescript_runner_does_not_execute_when_isolation_is_required_and_absent(monkeypatch):
    _configure(monkeypatch, sandbox="docker")
    _no_docker(monkeypatch)

    def _never(*args, **kwargs):
        raise AssertionError("code must not run on the host when Docker was required")

    monkeypatch.setattr(ts_runner, "_run_host", _never)
    monkeypatch.setattr(ts_runner, "_run_docker", _never)

    outs = ts_runner.run_functions_node("unused", "calc", "add", [[1, 2]])
    assert [(o.ok, o.error) for o in outs] == [(False, "sandbox_unavailable")]


def test_host_mode_still_executes_for_real(monkeypatch):
    """The unisolated path stays working — it is the default on a machine
    without Docker, and every existing run depends on it."""
    _configure(monkeypatch, sandbox="host")
    outs = py_runner.run_functions(FIXTURE, "models", "make_user", [[1, "Ada"]])
    assert outs[0].ok
    assert outs[0].value == {"id": 1, "name": "Ada"}


# --- the docker path is built correctly (without running Docker) ---

def test_python_docker_path_mounts_source_and_driver(monkeypatch):
    _configure(monkeypatch, sandbox="docker")
    monkeypatch.setattr(docker_runner, "docker_available", lambda: True)
    captured = {}

    def _fake_run(image_key, cmd, **kwargs):
        captured["image_key"] = image_key
        captured["cmd"] = cmd
        captured.update(kwargs)
        from codeshift.adapters.base import RunResult
        return RunResult(stdout='[{"ok": true, "value": 3}]', exit_code=0)

    monkeypatch.setattr(docker_runner, "run_in_container", _fake_run)
    outs = py_runner.run_functions(FIXTURE, "models", "make_user", [[1, "Ada"]])

    assert captured["image_key"] == "python"
    assert captured["cmd"][:3] == ["python", "-P", "/driver/_driver.py"]
    assert captured["cmd"][3] == "/work"          # the mount point, not a host path
    assert [m.container for m in captured["mounts"]] == ["/work", "/driver"]
    assert outs[0].ok and outs[0].value == 3


def test_typescript_docker_path_runs_baked_in_tsx_not_npx(monkeypatch):
    """--network none means anything npx would have to fetch cannot be fetched."""
    _configure(monkeypatch, sandbox="docker")
    monkeypatch.setattr(docker_runner, "docker_available", lambda: True)
    captured = {}

    def _fake_run(image_key, cmd, **kwargs):
        captured["image_key"] = image_key
        captured["cmd"] = cmd
        from codeshift.adapters.base import RunResult
        return RunResult(stdout="[]", exit_code=0)

    monkeypatch.setattr(docker_runner, "run_in_container", _fake_run)
    ts_runner.run_functions_node("unused", "calc", "add", [])

    assert captured["image_key"] == "node"
    assert captured["cmd"][0] == "tsx"
    assert "npx" not in captured["cmd"]


def test_docker_run_failure_is_not_read_as_a_behavioral_error(monkeypatch):
    _configure(monkeypatch, sandbox="docker")
    monkeypatch.setattr(docker_runner, "docker_available", lambda: True)

    from codeshift.adapters.base import RunResult
    monkeypatch.setattr(
        docker_runner, "run_in_container",
        lambda *a, **k: RunResult(stderr="sandbox unavailable", exit_code=EXIT_UNAVAILABLE),
    )
    outs = py_runner.run_functions(FIXTURE, "models", "make_user", [[1, "Ada"]])
    assert outs[0].error == "sandbox_unavailable"


# --- the images support the hardening they are run under ---

def test_dockerfiles_drop_root_and_bake_the_ts_runtime():
    images = Path(docker_runner.__file__).parent / "images"
    py = (images / "python.Dockerfile").read_text(encoding="utf-8")
    node = (images / "node.Dockerfile").read_text(encoding="utf-8")
    assert "USER 1000:1000" in py and "USER 1000:1000" in node
    assert "npm install -g tsx" in node   # --network none forbids fetching it later
