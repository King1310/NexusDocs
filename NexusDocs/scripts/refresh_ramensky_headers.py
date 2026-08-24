from database.repositories.territory_repository import TerritoryRepository
from domain.entities.territory import Territory
from domain.enums.organization_type import OrganizationType
from domain.value_objects.address import Address
from services.curated_header_service import CuratedHeaderService


def main() -> None:
    address = Address(
        region="Московская область",
        district="Раменский район",
        locality="п. Электроизолятор",
        city="",
        street="",
        house="",
        apartment="",
    )
    headers = CuratedHeaderService.resolve(address, tuple(OrganizationType))
    if len(headers) != len(OrganizationType):
        raise RuntimeError("Эталонный набор Раменского района неполон")

    territory = Territory(
        id=None,
        region=address.region,
        district=address.district,
        city=address.city,
        locality=address.locality,
        street=address.street,
    )
    TerritoryRepository().save_header_set(territory, list(headers.values()))
    print(f"Обновлено шапок: {len(headers)}")


if __name__ == "__main__":
    main()
