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
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraph


def _make_wallet(hotkey: str = 'validator-hotkey', hotkey_path: str | Path = '/tmp/wallets/validator/hotkeys/default'):
    return SimpleNamespace(
        hotkey=SimpleNamespace(ss58_address=hotkey),
        hotkey_file=SimpleNamespace(path=str(hotkey_path)),
    )


def _install_certificate_next_to_hotkey(source_path: str, tmp_path: Path) -> object:
    hotkey_path = tmp_path / 'wallets' / 'validator' / 'hotkeys' / 'default'
    hotkey_path.parent.mkdir(parents=True, exist_ok=True)
    destination = Path(str(hotkey_path) + '.cert.pem')
    destination.write_text(Path(source_path).read_text())
    return _make_wallet(hotkey_path=hotkey_path)


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
    """Install mocks around user code that constructs `ShieldMetagraph`.

    Example user file:

        # validator.py
        from bt_ddos_shield_client import ShieldMetagraph

        SOME_CONFIG_PROBABLY = load_config()  # this is subnet specific

        shield_metagraph = ShieldMetagraph(
            wallet=SOME_CONFIG_PROBABLY.wallet,
            netuid=SOME_CONFIG_PROBABLY.netuid,
            network=SOME_CONFIG_PROBABLY.network,
        )

        def send_message_to_all_neurons():
            shield_metagraph.sync()
            fox axon in shield_metagraph.axons:
                requests.post(f"http://{axon.ip}:{axon.port}/message", json={"message": "hello world"})}")

    Example test file:

        # test_validator.py
        from validator import send_message_to_all_neurons
        from bt_ddos_shield_client.testing import ShieldMetagraphTestRig

        def test_send_message_to_all_neurons(tmp_path):
            rig = ShieldMetagraphTestRig()
            rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
            rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
            rig.add_miner('miner-a', '198.51.100.10', 8080, shield_address='203.0.113.10:3030')

            with rig.install(tmp_path=tmp_path) as context:
                send_message_to_all_neurons()  # this will not make any external IO for the sake of the ddos shield


    The rig kicks in at `install()`: while the context is open,
    `ShieldMetagraph` still comes from user code, but its subtensor contact,
    wallet certificate, metagraph neurons, and HTTP miner manifests come from
    deterministic test doubles.
    """

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
        wallet = _install_certificate_next_to_hotkey(self.validator_certificate_path, tmp_path)
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
                    wallet=wallet,
                    netuid=7,
                    subtensor=object(),
                    sync=False,
                )


@dataclass(frozen=True)
class ShieldedNeuronMutatorContext:
    wallet: object
    netuid: int
    bittensor: object
    neurons: list[object]


@dataclass
class ShieldedNeuronMutatorTestRig:
    """Install mocks around user code that constructs `ShieldedNeuronMutator`.

    Example user file:

        # shield_client_user_code.py
        from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator

        async def shielded_neurons(wallet, netuid, bittensor, neurons):
            mutator = ShieldedNeuronMutator(wallet=wallet, netuid=netuid)
            return await mutator.mutate_neurons(bittensor, neurons)

        # validator.py
        import turbobt
        from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator

        SOME_CONFIG_PROBABLY = load_config()  # this is subnet specific

        mutator = ShieldedNeuronMutator(
            wallet=SOME_CONFIG_PROBABLY.wallet,
            netuid=SOME_CONFIG_PROBABLY.netuid,
        )

        bittensor = turbobt.bittensor(network=SOME_CONFIG_PROBABLY.network)

        sn = bittensor.subnet(SOME_CONFIG_PROBABLY.netuid)


        def send_message_to_all_neurons():

            shield_metagraph.sync()
            for neuron in await mutator.mutate_neurons(bittensor, await sn.list_neurons()):
                requests.post(f"http://{neuron.axon_info.ip}:{neuron.axon_info.port}/message",
                              json={"message": "hello world"})}")

    Example test file:

        # test_validator.py
        from bt_ddos_shield_client.testing import ShieldedNeuronMutatorTestRig
        from shield_client_user_code import shielded_neurons

        async def test_send_message_to_all_neurons(tmp_path):
            rig = ShieldedNeuronMutatorTestRig()
            rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
            rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
            rig.add_miner('miner-a', '198.51.100.20', 8090, shield_address='203.0.113.20:3040')

            with rig.install(tmp_path=tmp_path) as context:
                neurons = send_message_to_all_neurons()  # this will not make any external IO for the sake of the ddos shield

    The rig kicks in at `install()`: while the context is open,
    `ShieldedNeuronMutator` still comes from user code, but its default
    subtensor contact, wallet certificate, turbobt neurons, and HTTP miner
    manifests come from deterministic test doubles.
    """

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
        wallet = _install_certificate_next_to_hotkey(self.validator_certificate_path, tmp_path)
        neurons = [
            _make_turbobt_neuron(hotkey=miner.hotkey, ip=miner.ip, port=miner.port, uid=index)
            for index, miner in enumerate(self.miners)
        ]
        bittensor = turbobt.Bittensor('test', wallet=wallet)

        with patch(
            'bt_ddos_shield_client.shielded_turbobt.neuron_mutator.turbo_bittensor_subtensor_contact',
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

                yield ShieldedNeuronMutatorContext(
                    wallet=wallet,
                    netuid=7,
                    bittensor=bittensor,
                    neurons=neurons,
                )
