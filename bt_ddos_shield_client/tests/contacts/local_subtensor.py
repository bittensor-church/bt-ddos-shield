from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from bittensor import Subtensor
from bittensor.core.extrinsics.registration import burned_register_extrinsic, register_subnet_extrinsic
from bittensor.core.extrinsics.start_call import start_call_extrinsic
from bittensor.core.extrinsics.transfer import transfer_extrinsic
from bittensor.utils.balance import Balance
from bittensor_wallet import Wallet

if TYPE_CHECKING:
    from testcontainers.core.container import DockerContainer


LOCAL_SUBTENSOR_IMAGE = 'ghcr.io/opentensor/subtensor-localnet:devnet-ready'


@dataclass
class LocalSubtensorEnv:
    container: DockerContainer
    ws_endpoint: str
    wallet_root: Path
    subtensor: Subtensor
    alice_wallet: Wallet
    validator_wallet: Wallet
    miner_wallet: Wallet
    netuid: int

    def cleanup(self) -> None:
        try:
            self.subtensor.close()
        finally:
            try:
                self.container.stop()
            finally:
                shutil.rmtree(self.wallet_root, ignore_errors=True)


def _wait_for_chain_ready(subtensor: Subtensor, *, timeout_seconds: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            subtensor.get_subnets()
            return
        except Exception:
            time.sleep(1.0)
    raise RuntimeError('local subtensor did not become ready in time')


def _wait_for_ws_endpoint(ws_endpoint: str, *, timeout_seconds: float = 180.0) -> None:
    parsed = urlparse(ws_endpoint)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        raise RuntimeError(f'invalid websocket endpoint {ws_endpoint!r}')

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(1.0)
    raise RuntimeError(f'websocket endpoint {ws_endpoint} did not become ready in time')


def _wait_for_subnet(subtensor: Subtensor, netuid: int, *, timeout_seconds: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if subtensor.subnet_exists(netuid):
            return
        time.sleep(1.0)
    raise RuntimeError(f'subnet {netuid} did not become visible in time')


def _wait_for_new_subnet(
    subtensor: Subtensor,
    previous_subnets: set[int],
    *,
    timeout_seconds: float = 60.0,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current_subnets = set(subtensor.get_subnets())
        new_subnets = sorted(current_subnets - previous_subnets)
        if len(new_subnets) == 1:
            return new_subnets[0]
        if len(new_subnets) > 1:
            raise RuntimeError(f'expected one new subnet, got {new_subnets!r}')
        time.sleep(1.0)
    raise RuntimeError('new subnet did not become visible in time')


def _wait_for_registration(
    subtensor: Subtensor,
    hotkey: str,
    netuid: int,
    *,
    timeout_seconds: float = 120.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if subtensor.is_hotkey_registered_on_subnet(hotkey, netuid=netuid):
            return
        time.sleep(1.0)
    raise RuntimeError(f'hotkey {hotkey} did not register on subnet {netuid} in time')


def _make_wallet(wallet_root: Path, name: str, uri: str | None = None) -> Wallet:
    wallet = Wallet(path=str(wallet_root), name=name, hotkey='default')
    if uri is not None:
        wallet.create_coldkey_from_uri(uri, use_password=False, overwrite=True)
        wallet.create_hotkey_from_uri(uri, use_password=False, overwrite=True)
    else:
        wallet.create_new_coldkey(n_words=12, use_password=False, overwrite=True)
        wallet.create_new_hotkey(n_words=12, use_password=False, overwrite=True)
    return wallet


def _resolve_docker_host() -> str | None:
    if os.environ.get('DOCKER_HOST'):
        parsed = urlparse(os.environ['DOCKER_HOST'])
        if parsed.hostname:
            os.environ.setdefault('TESTCONTAINERS_HOST_OVERRIDE', parsed.hostname)
        return os.environ['DOCKER_HOST']

    try:
        current_context = subprocess.run(
            ['docker', 'context', 'show'],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not current_context:
            return None

        inspection = subprocess.run(
            ['docker', 'context', 'inspect', current_context],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        contexts = json.loads(inspection)
        if not contexts:
            return None
        endpoint = contexts[0].get('Endpoints', {}).get('docker', {}).get('Host')
        if not endpoint:
            return None
        os.environ['DOCKER_HOST'] = endpoint
        parsed = urlparse(endpoint)
        if parsed.hostname:
            os.environ.setdefault('TESTCONTAINERS_HOST_OVERRIDE', parsed.hostname)
        return endpoint
    except Exception:
        return None


def start_local_subtensor_env() -> LocalSubtensorEnv:
    _resolve_docker_host()
    from testcontainers.core.container import DockerContainer

    container = DockerContainer(LOCAL_SUBTENSOR_IMAGE)
    wallet_root = Path(tempfile.mkdtemp(prefix='shield-contact-wallets-'))
    subtensor: Subtensor | None = None
    try:
        container.with_exposed_ports(9944, 9945)
        container.start()
        ws_host = container.get_container_host_ip()
        ws_port = int(container.get_exposed_port(9945))
        ws_endpoint = f'ws://{ws_host}:{ws_port}'

        _wait_for_ws_endpoint(ws_endpoint)
        subtensor = Subtensor(network=ws_endpoint)
        _wait_for_chain_ready(subtensor)

        alice_wallet = _make_wallet(wallet_root, 'alice', '//Alice')
        validator_wallet = _make_wallet(wallet_root, 'validator')
        miner_wallet = _make_wallet(wallet_root, 'miner')

        transfer_extrinsic(
            subtensor,
            alice_wallet,
            validator_wallet.coldkeypub.ss58_address,
            Balance.from_tao(50_000),
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        transfer_extrinsic(
            subtensor,
            alice_wallet,
            miner_wallet.coldkeypub.ss58_address,
            Balance.from_tao(50_000),
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )

        before_subnets = set(subtensor.get_subnets())
        register_subnet_extrinsic(
            subtensor,
            alice_wallet,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        netuid = _wait_for_new_subnet(subtensor, before_subnets)
        _wait_for_subnet(subtensor, netuid)

        burned_register_extrinsic(
            subtensor,
            validator_wallet,
            netuid,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        if not subtensor.is_hotkey_registered_on_subnet(validator_wallet.hotkey.ss58_address, netuid=netuid):
            _wait_for_registration(subtensor, validator_wallet.hotkey.ss58_address, netuid)

        burned_register_extrinsic(
            subtensor,
            miner_wallet,
            netuid,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        if not subtensor.is_hotkey_registered_on_subnet(miner_wallet.hotkey.ss58_address, netuid=netuid):
            _wait_for_registration(subtensor, miner_wallet.hotkey.ss58_address, netuid)

        started, message = start_call_extrinsic(
            subtensor,
            alice_wallet,
            netuid,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )
        if not started:
            raise RuntimeError(f'failed to start local test subnet {netuid}: {message}')

        return LocalSubtensorEnv(
            container=container,
            ws_endpoint=ws_endpoint,
            wallet_root=wallet_root,
            subtensor=subtensor,
            alice_wallet=alice_wallet,
            validator_wallet=validator_wallet,
            miner_wallet=miner_wallet,
            netuid=netuid,
        )
    except Exception:
        if subtensor is not None:
            try:
                subtensor.close()
            except Exception:
                pass
        try:
            container.stop()
        finally:
            shutil.rmtree(wallet_root, ignore_errors=True)
        raise
