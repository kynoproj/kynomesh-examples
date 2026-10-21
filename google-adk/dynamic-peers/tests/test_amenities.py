from adk_travel.tools import hotel_amenities


def test_amenities_answers_the_breakfast_question():
    assert "breakfast not included ($15 add-on)" in hotel_amenities("Shinjuku Granbell")["result"]
    assert "breakfast included" in hotel_amenities("park hyatt tokyo")["result"]


def test_amenities_for_an_unknown_hotel_is_a_normal_reply():
    result = hotel_amenities("Atlantis Inn")
    assert result["status"] == "success"
    assert "No amenity information" in result["result"]
