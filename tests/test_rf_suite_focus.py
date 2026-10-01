from pathlib import Path

# the RF tier of this lab's suite (run-prplmesh-suite.py rf): the new contracts and the live
# RF rooms, without the room catalog or a soak
def test_focused_suite_runs_new_contracts_and_live_rooms_without_catalog_or_soak():
    source = Path(__file__).with_name("run-prplmesh-suite.py").read_text()
    focused = source.split("if 'rf' in chosen:", 1)[1].split("if 'rooms' in chosen:", 1)[0]
    assert "test_counter_guard.py" in focused and "test_rf_property_coverage.py" in focused
    assert "rf-property-rooms-smoke.py" in focused
    assert "counter-guard-room-smoke.py" in focused and "--shadow-counter-policy" in focused
    assert "room-feature-acceptance.js" not in focused and "churn-soak.sh" not in focused

