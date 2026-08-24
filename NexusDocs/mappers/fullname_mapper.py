from domain.value_objects.fullname import FullName


class FullNameMapper:

    @staticmethod
    def to_dict(full_name: FullName) -> dict:

        return {
            "last_name": full_name.last_name,
            "first_name": full_name.first_name,
            "middle_name": full_name.middle_name,
        }

    @staticmethod
    def from_dict(data: dict) -> FullName:

        return FullName(
            last_name=data["last_name"],
            first_name=data["first_name"],
            middle_name=data["middle_name"],
        )