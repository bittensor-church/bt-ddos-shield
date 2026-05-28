from __future__ import annotations

import base64
import json
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from ipaddress import ip_address

from bittensor.core.chain_data import AxonInfo, NeuronInfo, PrometheusInfo
from bittensor.utils.balance import Balance

from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact, _real_bittensor_subtensor_contacts
from bt_ddos_shield_client.encryption import ECIESEncryptionManager


def _make_bittensor_neuron(*, hotkey: str, ip: str, port: int, uid: int, netuid: int) -> NeuronInfo:
    return NeuronInfo(
        hotkey=hotkey,
        coldkey='miner-coldkey',
        uid=uid,
        netuid=netuid,
        active=1,
        stake=Balance.from_tao(0),
        stake_dict={},
        total_stake=Balance.from_tao(0),
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        weights=[],
        bonds=[],
        pruning_score=0,
        prometheus_info=PrometheusInfo(block=0, version=1, ip='127.0.0.1', port=9090, ip_type=4),
        axon_info=AxonInfo(version=1, ip=ip, port=port, ip_type=4, hotkey=hotkey, coldkey='miner-coldkey'),
    )


def _build_manifest_body(public_key: str, address: str, validator_hotkey: str) -> bytes:
    encrypted = ECIESEncryptionManager().encrypt(public_key, address.encode())
    return json.dumps(
        {
            'ddos_shield_manifest': {
                'encrypted_url_mapping': {
                    validator_hotkey: base64.b64encode(encrypted).decode(),
                },
            }
        }
    ).encode()


def _make_turbobt_neuron(*, hotkey: str, ip: str, port: int, uid: int, netuid: int):
    # Optional dependency import; base testing helpers must load without turbobt installed.
    import turbobt
    from turbobt.neuron import AxonInfo as TurboAxonInfo
    from turbobt.neuron import AxonProtocolEnum, Neuron as TurboNeuron, PrometheusInfo as TurboPrometheusInfo

    return TurboNeuron(
        subnet=turbobt.Subnet(
            object(),
            netuid=netuid,
            name='test-subnet',
            symbol='TS',
            tempo=0,
            owner_hotkey='owner-hotkey',
            owner_coldkey='owner-coldkey',
            identity={},
        ),
        uid=uid,
        coldkey='miner-coldkey',
        hotkey=hotkey,
        active=True,
        axon_info=TurboAxonInfo(ip=ip_address(ip), port=port, protocol=AxonProtocolEnum.HTTP),
        prometheus_info=TurboPrometheusInfo(ip=ip_address('127.0.0.1'), port=9090),
        stake=0.0,
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        pruning_score=0,
    )


@dataclass(frozen=True)
class _MinerFixture:
    hotkey: str
    ip: str
    port: int
    shield_address: str | None


@dataclass(frozen=True)
class ShieldTestRigContext:
    wallet: object
    netuid: int
    bittensor: object | None
    neurons: list[object]


@dataclass
class ShieldTestRig:
    wallet: object
    netuid: int = 7
    with_turbobt: bool = False
    miners: list[_MinerFixture] = field(default_factory=list)

    def add_miner(self, hotkey: str, ip: str, port: int, *, shield_address: str | None) -> None:
        self.miners.append(_MinerFixture(hotkey=hotkey, ip=ip, port=port, shield_address=shield_address))

    @contextmanager
    def install(self):
        self._assert_no_real_contacts()

        # Test-only dependency import; keep package import light for downstream users.
        from aioresponses import aioresponses

        certificate = ShieldClient(wallet=self.wallet).certificate
        validator_hotkey = self.wallet.hotkey.ss58_address
        bittensor_contact = MockBittensorSubtensorContact(expected_hotkey=validator_hotkey)
        bittensor_contact.set_metagraph_sync(
            [
                _make_bittensor_neuron(
                    hotkey=miner.hotkey,
                    ip=miner.ip,
                    port=miner.port,
                    uid=index,
                    netuid=self.netuid,
                )
                for index, miner in enumerate(self.miners)
            ]
        )

        with ExitStack() as stack:
            stack.enter_context(
                self._patch(
                    'bt_ddos_shield_client.shield_metagraph.bittensor_subtensor_contact',
                    lambda: bittensor_contact,
                )
            )
            bittensor, neurons = self._install_turbobt(stack, validator_hotkey)
            mocked = stack.enter_context(aioresponses())
            self._mock_miner_manifests(mocked, certificate.public_key, validator_hotkey)

            yield ShieldTestRigContext(
                wallet=self.wallet,
                netuid=self.netuid,
                bittensor=bittensor,
                neurons=neurons,
            )

    def _assert_no_real_contacts(self) -> None:
        if len(_real_bittensor_subtensor_contacts) > 0:
            raise AssertionError(
                'Real subtensor contact was already instantiated before test rig install. '
                'Install the rig before calling sync/mutate_neurons/listing code.'
            )
        if not self.with_turbobt:
            return
        try:
            # Optional dependency import; this guard only matters when turbobt support is requested.
            from bt_ddos_shield_client.shielded_turbobt.contacts import _real_turbo_bittensor_subtensor_contacts
        except ImportError:
            return
        if len(_real_turbo_bittensor_subtensor_contacts) > 0:
            raise AssertionError(
                'Real subtensor contact was already instantiated before test rig install. '
                'Install the rig before calling sync/mutate_neurons/listing code.'
            )

    def _install_turbobt(self, stack: ExitStack, validator_hotkey: str) -> tuple[object | None, list[object]]:
        if not self.with_turbobt:
            return None, []

        try:
            # Optional dependency import; raise a focused error only when turbobt mode is used.
            import turbobt

            from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact
        except ImportError as exc:
            raise RuntimeError(
                'ShieldTestRig with_turbobt=True requires turbobt. '
                'Install bt_ddos_shield_client[turbobt] to use turbobt test rig support.'
            ) from exc

        neurons = [
            _make_turbobt_neuron(
                hotkey=miner.hotkey,
                ip=miner.ip,
                port=miner.port,
                uid=index,
                netuid=self.netuid,
            )
            for index, miner in enumerate(self.miners)
        ]
        contact = MockTurboBittensorSubtensorContact(expected_hotkey=validator_hotkey)
        contact.set_neuron_listing(neurons)
        bittensor = turbobt.Bittensor('test', wallet=self.wallet)

        async def list_neurons(_subnet, block_hash=None):
            return neurons

        stack.enter_context(
            self._patch(
                'bt_ddos_shield_client.shielded_turbobt.neuron_mutator.turbo_bittensor_subtensor_contact',
                lambda: contact,
            )
        )
        stack.enter_context(self._patch('turbobt.subnet.SubnetReference.list_neurons', list_neurons))
        return bittensor, neurons

    def _mock_miner_manifests(self, mocked, public_key: str, validator_hotkey: str) -> None:
        for miner in self.miners:
            url = f'http://{miner.ip}:{miner.port}/shield_manifest.json'
            if miner.shield_address is None:
                mocked.get(url, status=404, repeat=True)
                continue
            mocked.get(
                url,
                status=200,
                body=_build_manifest_body(public_key, miner.shield_address, validator_hotkey),
                repeat=True,
            )

    @contextmanager
    def _patch(self, target: str, value):
        # Local import keeps unittest.mock out of the normal package import path.
        from unittest.mock import patch

        with patch(target, value):
            yield
