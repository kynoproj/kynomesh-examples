from claude_travel.tools import hotel_amenities


async def test_amenities_answers_the_breakfast_question():
    result = await hotel_amenities.handler({"hotel": "Shinjuku Granbell"})
    assert "breakfast not included ($15 add-on)" in result["content"][0]["text"]


async def test_amenities_for_an_unknown_hotel_is_a_normal_reply():
    result = await hotel_amenities.handler({"hotel": "Atlantis Inn"})
    assert "No amenity information" in result["content"][0]["text"]
    assert "is_error" not in result


async def test_amenities_missing_argument_is_reported_to_the_model():
    assert (await hotel_amenities.handler({}))["is_error"] is True
