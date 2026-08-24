from domain.enums.base_enum import BaseEnum


class SochDuration(BaseEnum):
    OVER_TWO_DAYS = "Свыше двух суток, но не более десяти"
    OVER_TEN_DAYS = "Свыше 10 суток, но не более одного месяца"
    OVER_MONTH = "Свыше одного месяца"