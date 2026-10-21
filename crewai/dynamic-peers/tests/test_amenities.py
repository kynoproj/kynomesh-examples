from crew_travel.tools import hotel_amenities


def test_amenities_answers_the_breakfast_question():
    assert "breakfast not included ($15 add-on)" in hotel_amenities.run(hotel="Shinjuku Granbell")
    assert "breakfast included" in hotel_amenities.run(hotel="park hyatt tokyo")


def test_amenities_for_an_unknown_hotel_is_a_normal_reply():
    assert "No amenity information" in hotel_amenities.run(hotel="Atlantis Inn")
