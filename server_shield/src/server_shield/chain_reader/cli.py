from server_shield.chain_reader.chain import fetch_validators_with_certs
from server_shield.chain_reader.reconciliation import reconcile_desired_domains
from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_desired_domains,
    read_root_domain,
    write_desired_domains,
)


def _run_once() -> int:
    ensure_state_files()
    root_domain = read_root_domain()
    if root_domain.domain is None:
        print("skipping chain_reader because root_domain is null", flush=True)
        return 0

    config = get_config()
    blacklist = set(read_blacklist().root)
    current_domains = read_desired_domains().domains
    validators = fetch_validators_with_certs(config)

    for validator in validators:
        if validator.hotkey in blacklist:
            print(f"excluding blacklisted validator {validator.hotkey}", flush=True)
        elif validator.public_cert is None:
            print(
                f"excluding validator {validator.hotkey}: {validator.cert_invalid_reason}",
                flush=True,
            )

    result = reconcile_desired_domains(
        root_domain=root_domain.domain,
        current_domains=current_domains,
        validators=validators,
        blacklist=blacklist,
    )
    write_desired_domains(
        domains={
            hotkey: entry.model_dump()
            for hotkey, entry in result.desired_domains.items()
        }
    )
    print(
        "chain_reader reconciled "
        f"observed={result.observed} kept={result.kept} created={result.created} "
        f"rotated_for_cert={result.rotated_for_cert} "
        f"rotated_for_root_domain={result.rotated_for_root_domain} "
        f"removed={result.removed} blacklisted={result.blacklisted} "
        f"invalid_cert={result.invalid_cert}",
        flush=True,
    )
    return 0


def main() -> int:
    get_config()
    return run_component("chain-reader", _run_once)


if __name__ == "__main__":
    raise SystemExit(main())
