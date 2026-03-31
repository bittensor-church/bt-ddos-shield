from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import bittensor
import bittensor_wallet


@dataclass(frozen=True)
class ValidatorCertificateRecord:
    hotkey: str
    certificate_payload: dict[str, Any] | None


@dataclass(frozen=True)
class NeuronAxonRecord:
    is_null: bool
    is_serving: bool
    ip: str | None
    port: int | None


@dataclass(frozen=True)
class SubtensorContactCall:
    method: str
    netuid: int | None = None
    hotkey_ss58: str | None = None
    ip: str | None = None
    port: int | None = None


class AbstractSubtensorContact(ABC):
    @abstractmethod
    def list_validator_certificates(self, *, netuid: int) -> list[ValidatorCertificateRecord]:
        raise NotImplementedError

    @abstractmethod
    def is_hotkey_registered(self, *, hotkey_ss58: str, netuid: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_neuron_axon(self, *, hotkey_ss58: str, netuid: int) -> NeuronAxonRecord:
        raise NotImplementedError

    @abstractmethod
    def publish_axon(
        self,
        *,
        wallet: bittensor_wallet.Wallet,
        netuid: int,
        ip: str,
        port: int,
    ) -> bool:
        raise NotImplementedError


class BittensorSubtensorContact(AbstractSubtensorContact):
    def __init__(self, subtensor_address: str) -> None:
        self._subtensor = bittensor.subtensor(subtensor_address)

    def list_validator_certificates(self, *, netuid: int) -> list[ValidatorCertificateRecord]:
        metagraph = bittensor.metagraph(netuid=netuid, subtensor=self._subtensor)
        records: list[ValidatorCertificateRecord] = []
        for hotkey, permit in zip(metagraph.hotkeys, metagraph.validator_permit, strict=False):
            if not bool(permit):
                continue
            records.append(
                ValidatorCertificateRecord(
                    hotkey=hotkey,
                    certificate_payload=self._subtensor.query_subtensor(
                        name="NeuronCertificates",
                        params=[netuid, hotkey],
                    ),
                )
            )
        return records

    def is_hotkey_registered(self, *, hotkey_ss58: str, netuid: int) -> bool:
        return self._subtensor.is_hotkey_registered(hotkey_ss58, netuid)

    def get_neuron_axon(self, *, hotkey_ss58: str, netuid: int) -> NeuronAxonRecord:
        uid = self._subtensor.get_uid_for_hotkey_on_subnet(hotkey_ss58, netuid)
        neuron = self._subtensor.neuron_for_uid(uid, netuid)
        return NeuronAxonRecord(
            is_null=bool(neuron.is_null),
            is_serving=bool(neuron.axon_info.is_serving),
            ip=neuron.axon_info.ip,
            port=neuron.axon_info.port,
        )

    def publish_axon(
        self,
        *,
        wallet: bittensor_wallet.Wallet,
        netuid: int,
        ip: str,
        port: int,
    ) -> bool:
        return bool(
            self._subtensor.serve_axon(
                netuid,
                axon=bittensor.Axon(
                    wallet,
                    port=port,
                    ip=ip,
                    external_ip=ip,
                    external_port=port,
                ),
                wait_for_inclusion=True,
                wait_for_finalization=True,
            )
        )


@dataclass
class MockSubtensorContact(AbstractSubtensorContact):
    validator_certificates: list[ValidatorCertificateRecord] = field(default_factory=list)
    validator_certificates_exception: Exception | None = None
    registrations: dict[tuple[str, int], bool] = field(default_factory=dict)
    neuron_axons: dict[tuple[str, int], NeuronAxonRecord] = field(default_factory=dict)
    publish_result: bool = True
    publish_exception: Exception | None = None
    calls: list[SubtensorContactCall] = field(default_factory=list)

    def set_validator_certificates(
        self,
        records: list[ValidatorCertificateRecord],
        *,
        exception: Exception | None = None,
    ) -> None:
        self.validator_certificates = list(records)
        self.validator_certificates_exception = exception

    def set_registration(self, *, hotkey_ss58: str, netuid: int, registered: bool) -> None:
        self.registrations[(hotkey_ss58, netuid)] = registered

    def set_neuron_axon(
        self,
        *,
        hotkey_ss58: str,
        netuid: int,
        neuron_axon: NeuronAxonRecord,
    ) -> None:
        self.neuron_axons[(hotkey_ss58, netuid)] = neuron_axon

    def set_publish_behavior(
        self,
        *,
        result: bool = True,
        exception: Exception | None = None,
    ) -> None:
        self.publish_result = result
        self.publish_exception = exception

    def reset_calls(self) -> None:
        self.calls.clear()

    def list_validator_certificates(self, *, netuid: int) -> list[ValidatorCertificateRecord]:
        self.calls.append(SubtensorContactCall(method="list_validator_certificates", netuid=netuid))
        if self.validator_certificates_exception is not None:
            raise self.validator_certificates_exception
        return list(self.validator_certificates)

    def is_hotkey_registered(self, *, hotkey_ss58: str, netuid: int) -> bool:
        self.calls.append(
            SubtensorContactCall(
                method="is_hotkey_registered",
                netuid=netuid,
                hotkey_ss58=hotkey_ss58,
            )
        )
        return self.registrations.get((hotkey_ss58, netuid), False)

    def get_neuron_axon(self, *, hotkey_ss58: str, netuid: int) -> NeuronAxonRecord:
        self.calls.append(
            SubtensorContactCall(
                method="get_neuron_axon",
                netuid=netuid,
                hotkey_ss58=hotkey_ss58,
            )
        )
        return self.neuron_axons[(hotkey_ss58, netuid)]

    def publish_axon(
        self,
        *,
        wallet: bittensor_wallet.Wallet,
        netuid: int,
        ip: str,
        port: int,
    ) -> bool:
        self.calls.append(
            SubtensorContactCall(
                method="publish_axon",
                netuid=netuid,
                hotkey_ss58=wallet.hotkey.ss58_address,
                ip=ip,
                port=port,
            )
        )
        if self.publish_exception is not None:
            raise self.publish_exception
        return self.publish_result


_contact_instance: AbstractSubtensorContact | None = None


def subtensor_contact(subtensor_address: str) -> AbstractSubtensorContact:
    global _contact_instance
    if _contact_instance is None:
        _contact_instance = BittensorSubtensorContact(subtensor_address)
    return _contact_instance
