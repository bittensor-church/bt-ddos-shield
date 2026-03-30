import sys

from server_shield.pulumi_runner.cli import invoke_pulumi_cli


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return invoke_pulumi_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
