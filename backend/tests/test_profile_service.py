from services.profile_service import calculate_completeness

def test_completeness():
    data = {"personal": {"name": "A", "email": "a@b.com"}, "professional": {"headline": "Engineer"}}
    pct = calculate_completeness(data)
    assert pct > 0
