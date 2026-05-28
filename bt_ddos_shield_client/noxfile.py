from __future__ import annotations

import nox


PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["tests"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run the default pytest suite."""
    session.run_install(
        "uv",
        "sync",
        "--locked",
        "--group",
        "test",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("pytest", *(session.posargs or ("tests", "-v")))
