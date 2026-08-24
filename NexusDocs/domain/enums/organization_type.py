from domain.enums.base_enum import BaseEnum


class OrganizationType(BaseEnum):
    """Девять обязательных адресатов служебного запроса."""

    MILITARY_COMMISSARIAT = "Военный комиссариат"
    MILITARY_COMMANDANT = "Военная комендатура"
    NARCOLOGY = "Наркологическая служба"
    PSYCHIATRY = "Психиатрическая служба"
    HOSPITAL = "ЦРБ / ЦГБ"
    TFOMS = "ТФОМС"
    ADMINISTRATION = "Администрация"
    CONTRACT_SERVICE_POINT = "Пункт отбора на военную службу по контракту"
    ELECTION_COMMISSION = "Территориальная избирательная комиссия"

    @property
    def slug(self) -> str:
        return {
            self.MILITARY_COMMISSARIAT: "voenkomat",
            self.MILITARY_COMMANDANT: "komendatura",
            self.NARCOLOGY: "narkologiya",
            self.PSYCHIATRY: "psihiatriya",
            self.HOSPITAL: "bolnica",
            self.TFOMS: "tfoms",
            self.ADMINISTRATION: "administraciya",
            self.CONTRACT_SERVICE_POINT: "punkt_otbora",
            self.ELECTION_COMMISSION: "tik",
        }[self]
