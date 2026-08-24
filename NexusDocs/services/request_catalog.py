from __future__ import annotations

from dataclasses import dataclass

from domain.enums.organization_type import OrganizationType


@dataclass(frozen=True, slots=True)
class RequestTemplate:
    number: int
    slug: str
    title: str
    filename: str
    organization_type: OrganizationType | None = None

    @property
    def requires_resolved_header(self) -> bool:
        return self.organization_type is not None


REQUEST_CATALOG = (
    RequestTemplate(1, "military_unit", "Запрос в воинскую часть", "01_military_unit.docx"),
    RequestTemplate(2, "zags", "Запрос в орган ЗАГС", "02_zags.docx"),
    RequestTemplate(3, "military_commissariat", "Запрос в военный комиссариат", "03_military_commissariat.docx", OrganizationType.MILITARY_COMMISSARIAT),
    RequestTemplate(4, "military_commandant", "Запрос военному коменданту", "04_military_commandant.docx", OrganizationType.MILITARY_COMMANDANT),
    RequestTemplate(5, "narcology", "Запрос в наркологическую службу", "05_narcology.docx", OrganizationType.NARCOLOGY),
    RequestTemplate(6, "psychiatry", "Запрос в психиатрическую службу", "06_psychiatry.docx", OrganizationType.PSYCHIATRY),
    RequestTemplate(7, "hospital", "Запрос в медицинскую организацию", "07_hospital.docx", OrganizationType.HOSPITAL),
    RequestTemplate(8, "tfoms", "Запрос в ТФОМС", "08_tfoms.docx", OrganizationType.TFOMS),
    RequestTemplate(9, "higher_investigation", "Запрос вышестоящему следственному органу", "09_higher_investigation.docx"),
    RequestTemplate(10, "mvd_local", "Запрос в территориальный орган МВД", "10_mvd_local.docx"),
    RequestTemplate(11, "mvd_regional", "Запрос в региональный орган МВД", "11_mvd_regional.docx"),
    RequestTemplate(12, "administration", "Запрос в администрацию", "12_administration.docx", OrganizationType.ADMINISTRATION),
    RequestTemplate(13, "contract_service_point", "Запрос в пункт отбора на военную службу", "13_contract_service_point.docx", OrganizationType.CONTRACT_SERVICE_POINT),
    RequestTemplate(14, "military_social_center", "Запрос в военно-социальный центр", "14_military_social_center.docx"),
    RequestTemplate(15, "election_commission", "Запрос в территориальную избирательную комиссию", "15_election_commission.docx", OrganizationType.ELECTION_COMMISSION),
)
