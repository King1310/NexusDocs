from domain.value_objects.passport import Passport


class PassportMapper:

    @staticmethod
    def to_dict(passport: Passport | None) -> dict:

        if passport is None:
            return {
                "passport_series": None,
                "passport_number": None,
                "passport_issued_by": None,
            }

        return {

            "passport_series": passport.series,

            "passport_number": passport.number,

            "passport_issued_by": passport.issued_by,
        }