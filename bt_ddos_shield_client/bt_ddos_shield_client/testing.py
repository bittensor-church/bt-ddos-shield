from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bittensor.core.chain_data import AxonInfo, NeuronInfo, PrometheusInfo
from bittensor.utils.balance import Balance

from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact
from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraph, ShieldMetagraphOptions


def _make_wallet(hotkey: str = 'validator-hotkey'):
    return SimpleNamespace(hotkey=SimpleNamespace(ss58_address=hotkey))


def _make_bittensor_neuron(*, hotkey: str, ip: str, port: int, uid: int) -> NeuronInfo:
    return NeuronInfo(
        hotkey=hotkey,
        coldkey='miner-coldkey',
        uid=uid,
        netuid=7,
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


def _build_manifest_body(public_key: str, address: str, validator_hotkey: str = 'validator-hotkey') -> bytes:
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


def _make_turbobt_neuron(*, hotkey: str, ip: str, port: int, uid: int):
    import turbobt
    from turbobt.neuron import AxonInfo as TurboAxonInfo
    from turbobt.neuron import AxonProtocolEnum, Neuron as TurboNeuron, PrometheusInfo as TurboPrometheusInfo

    return TurboNeuron(
        subnet=turbobt.Subnet(
            object(),
            netuid=7,
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


def _make_mock_turbo_bittensor_contact():
    from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact

    return MockTurboBittensorSubtensorContact()


@dataclass(frozen=True)
class _MinerFixture:
    hotkey: str
    ip: str
    port: int
    shield_address: str | None


@dataclass
class ShieldMetagraphTestRig:
    miners: list[_MinerFixture] = field(default_factory=list)
    contact: MockBittensorSubtensorContact = field(default_factory=MockBittensorSubtensorContact)
    validator_certificate_path: str | None = None

    def set_validator_certificate_path(self, path: str | Path) -> None:
        self.validator_certificate_path = str(path)

    def set_on_chain_certificate(
        self,
        public_key: str | None,
        *,
        exception: Exception | None = None,
    ) -> None:
        self.contact.set_own_certificate(public_key, exception=exception)

    def set_upload_behavior(self, exception: Exception | None = None) -> None:
        self.contact.set_upload_behavior(exception)

    def add_miner(self, hotkey: str, ip: str, port: int, *, shield_address: str | None) -> None:
        self.miners.append(_MinerFixture(hotkey=hotkey, ip=ip, port=port, shield_address=shield_address))

    @contextmanager
    def install(self, *, tmp_path):
        if self.validator_certificate_path is None:
            raise ValueError('validator_certificate_path must be configured')

        from aioresponses import aioresponses

        certificate = EDDSACertificateManager.load_certificate(self.validator_certificate_path)
        destination = tmp_path / 'validator.pem'
        destination.write_text(Path(self.validator_certificate_path).read_text())
        self.contact.set_metagraph_sync(
            [
                _make_bittensor_neuron(hotkey=miner.hotkey, ip=miner.ip, port=miner.port, uid=index)
                for index, miner in enumerate(self.miners)
            ]
        )

        with patch(
            'bt_ddos_shield_client.shield_metagraph.bittensor_subtensor_contact',
            return_value=self.contact,
        ):
            with aioresponses() as mocked:
                for miner in self.miners:
                    url = f'http://{miner.ip}:{miner.port}/shield_manifest.json'
                    if miner.shield_address is None:
                        mocked.get(url, status=404, repeat=True)
                        continue
                    mocked.get(
                        url,
                        status=200,
                        body=_build_manifest_body(certificate.public_key, miner.shield_address),
                        repeat=True,
                    )

                yield ShieldMetagraph(
                    wallet=_make_wallet(),
                    netuid=7,
                    subtensor=object(),
                    sync=False,
                    options=ShieldMetagraphOptions(certificate_path=str(destination)),
                )


@dataclass(frozen=True)
class ShieldedNeuronMutatorContext:
    wallet: object
    netuid: int
    ddos_shield_options: ShieldMetagraphOptions
    bittensor: object
    neurons: list[object]


@dataclass
class ShieldedNeuronMutatorTestRig:
    miners: list[_MinerFixture] = field(default_factory=list)
    contact: object = field(default_factory=_make_mock_turbo_bittensor_contact)
    validator_certificate_path: str | None = None

    def set_validator_certificate_path(self, path: str | Path) -> None:
        self.validator_certificate_path = str(path)

    def set_on_chain_certificate(
        self,
        public_key: str | None,
        *,
        exception: Exception | None = None,
    ) -> None:
        self.contact.set_own_certificate(public_key, exception=exception)

    def set_upload_behavior(self, exception: Exception | None = None) -> None:
        self.contact.set_upload_behavior(exception)

    def add_miner(self, hotkey: str, ip: str, port: int, *, shield_address: str | None) -> None:
        self.miners.append(_MinerFixture(hotkey=hotkey, ip=ip, port=port, shield_address=shield_address))

    @contextmanager
    def install(self, *, tmp_path):
        if self.validator_certificate_path is None:
            raise ValueError('validator_certificate_path must be configured')

        import turbobt

        from aioresponses import aioresponses

        certificate = EDDSACertificateManager.load_certificate(self.validator_certificate_path)
        destination = tmp_path / 'validator.pem'
        destination.write_text(Path(self.validator_certificate_path).read_text())
        neurons = [
            _make_turbobt_neuron(hotkey=miner.hotkey, ip=miner.ip, port=miner.port, uid=index)
            for index, miner in enumerate(self.miners)
        ]
        wallet = _make_wallet()
        ddos_shield_options = ShieldMetagraphOptions(certificate_path=str(destination))
        bittensor = turbobt.Bittensor('test', wallet=wallet)

        with aioresponses() as mocked:
            for miner in self.miners:
                url = f'http://{miner.ip}:{miner.port}/shield_manifest.json'
                if miner.shield_address is None:
                    mocked.get(url, status=404, repeat=True)
                    continue
                mocked.get(
                    url,
                    status=200,
                    body=_build_manifest_body(certificate.public_key, miner.shield_address),
                    repeat=True,
                )

            yield ShieldedNeuronMutatorContext(
                wallet=wallet,
                netuid=7,
                ddos_shield_options=ddos_shield_options,
                bittensor=bittensor,
                neurons=neurons,
            )
