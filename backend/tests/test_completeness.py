from services.profile_service import calculate_completeness

def test_completeness_deterministic():
    data = {"personal": {"name": "A", "email": "a@b.com", "location": "X"}, "professional": {"headline": "Eng"}}
    pct = calculate_completeness(data)
    assert pct >= 0 and pct <= 100
    # Same input same output
    assert calculate_completeness(data) == pct
