from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Investigator:
    key: str
    full_name: str
    initials_surname: str
    surname_initials: str
    position_short: str
    rank: str
    signature_filename: str
    position_form: str
    form_role_hint: str
    form_rank: str
    form_rank_label: str
    table_name: str

    @property
    def position_long(self) -> str:
        return f"{self.position_short} военного следственного отдела"

    @property
    def position_table(self) -> str:
        return self.position_short

    @property
    def display_name(self) -> str:
        return f"{self.surname_initials} — {self.position_short}"

    def replacements(self) -> dict[str, str]:
        names = (
            "position_long", "position_short", "position_table", "position_form",
            "rank", "initials_surname", "surname_initials", "form_role_hint",
            "form_rank", "form_rank_label", "table_name",
        )
        return {"{{INVESTIGATOR_" + name.upper() + "}}": getattr(self, name)
                for name in names}


TSOMARTOV = Investigator(
    "tsomartov", "Цомартов С.А.", "С.А. Цомартов", "Цомартов С.А.",
    "Следователь", "лейтенант юстиции", "tsomartov_sa.png",
    "Следователь отдела", "(заместитель, следователь)", "лейтенант юстиции",
    "(в звании)", "Цомартов С.А.",
)
LITVINOV = Investigator(
    "litvinov", "Литвинов Виктор Николаевич", "В.Н. Литвинов", "Литвинов В.Н.",
    "Заместитель руководителя", "подполковник юстиции", "litvinov_vn.png",
    "Заместитель руководителя", "(заместитель)", "", "", "Литвинов В.Н.",
)
SARKISYAN = Investigator(
    "sarkisyan", "Саркисян Анатолий Кароевич", "А.К. Саркисян", "Саркисян А.К.",
    "Старший следователь-криминалист", "подполковник юстиции", "sarkisyan_ak.png",
    "Старший следователь-криминалист", "(заместитель, следователь)", "", "", "А.К. Саркисян",
)
INVESTIGATORS = (TSOMARTOV, LITVINOV, SARKISYAN)


def investigator_from_key(key: str | None) -> Investigator:
    if not key:
        return TSOMARTOV
    for profile in INVESTIGATORS:
        if profile.key == key:
            return profile
    raise ValueError(f"Неизвестный исполнитель: {key}")
