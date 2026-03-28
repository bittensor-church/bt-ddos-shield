from server_shield.shared.runtime import run_component


def test_run_component_returns_zero_for_success(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "server_shield.shared.runtime.init_sentry",
        lambda component_name: calls.append(component_name),
    )

    exit_code = run_component("chain-reader", lambda: 0)

    assert exit_code == 0
    assert calls == ["chain-reader"]


def test_run_component_reports_non_zero_exit_codes(monkeypatch) -> None:
    reports: list[tuple[str, int, str]] = []
    monkeypatch.setattr("server_shield.shared.runtime.init_sentry", lambda component_name: None)
    monkeypatch.setattr(
        "server_shield.shared.runtime.capture_component_failure",
        lambda component_name, exit_code, detail: reports.append((component_name, exit_code, detail)),
    )

    exit_code = run_component("pulumi-runner", lambda: 7)

    assert exit_code == 7
    assert reports == [("pulumi-runner", 7, "non-zero exit")]


def test_run_component_reports_uncaught_exceptions(monkeypatch) -> None:
    reports: list[tuple[str, int, str]] = []
    monkeypatch.setattr("server_shield.shared.runtime.init_sentry", lambda component_name: None)
    monkeypatch.setattr(
        "server_shield.shared.runtime.capture_component_failure",
        lambda component_name, exit_code, detail: reports.append((component_name, exit_code, detail)),
    )

    def boom() -> int:
        raise RuntimeError("kaboom")

    exit_code = run_component("chain-writer", boom)

    assert exit_code == 1
    assert reports == [("chain-writer", 1, "uncaught exception: kaboom")]
