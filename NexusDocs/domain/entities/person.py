from __future__ import annotations

from dataclasses import dataclass

from domain.entities.base_entity import BaseEntity
from domain.value_objects.birth import Birth
from domain.value_objects.document_info import DocumentInfo
from domain.value_objects.fullname import FullName
from domain.value_objects.military import Military
from domain.value_objects.passport import Passport
from domain.value_objects.address import Address
from domain.value_objects.soch_case import SochCase


@dataclass(slots=True)
class Person(BaseEntity):
    """
    Основная сущность человека.
    """

    id: int

    full_name: FullName

    passport: Passport | None

    birth: Birth

    registration_address: Address

    military: Military

    soch_case: SochCase

    document_info: DocumentInfo

    def __str__(self) -> str:
        return (
            f"{self.id} — {self.full_name}"
        )