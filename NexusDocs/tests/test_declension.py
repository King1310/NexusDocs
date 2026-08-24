from domain.value_objects.fullname import FullName
from utils.declension import decline_full_name, rank_genitive


def test_declines_common_male_full_name():
    declined = decline_full_name(
        FullName("Иванов", "Иван", "Иванович")
    )

    assert declined.last_name_genitive == "Иванова"
    assert declined.first_name_genitive == "Ивана"
    assert declined.middle_name_genitive == "Ивановича"
    assert declined.last_name_instrumental == "Ивановым"


def test_declines_compound_rank():
    assert rank_genitive("старший лейтенант") == "старшего лейтенанта"
