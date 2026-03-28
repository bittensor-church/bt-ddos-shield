import sys

from server_shield.shared.sentry import capture_component_failure, init_sentry


def main() -> int:
    component_name = sys.argv[1]
    exit_code = int(sys.argv[2])
    detail = sys.argv[3]
    init_sentry(component_name)
    capture_component_failure(component_name, exit_code, detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
