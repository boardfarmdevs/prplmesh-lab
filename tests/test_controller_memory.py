import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("controller_memory", Path(__file__).with_name("controller-memory.py"))
MEMORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEMORY)


def test_growth_and_absolute_limit_are_independent():
    samples = [{"pid": 10, "rss_kib": value * 1024} for value in (100, 110, 105)]
    assert MEMORY.evaluate(samples, 10, 110)["passed"]
    assert not MEMORY.evaluate(samples, 9, 110)["passed"]
    assert not MEMORY.evaluate(samples, 10, 109)["passed"]


@pytest.mark.parametrize("samples", [[], [{"pid": 1, "rss_kib": 10}],
                                     [{"pid": 1, "rss_kib": 10}, {"pid": 2, "rss_kib": 10}]])
def test_restart_or_missing_samples_cannot_pass(samples):
    with pytest.raises(RuntimeError):
        MEMORY.evaluate(samples, 64, 1024)


def test_exact_roster_rejects_duplicates_and_missing_nodes():
    topology = {"devices": [{"radios": [{"bsses": [{"clients": [{"id": str(index)}]}]}]}
                            for index in range(5)]}
    assert MEMORY.roster(topology, 5) == [str(index) for index in range(5)]
    topology["devices"][1]["radios"][0]["bsses"][0]["clients"][0]["id"] = "0"
    with pytest.raises(RuntimeError):
        MEMORY.roster(topology, 5)
    topology["devices"].pop()
    with pytest.raises(RuntimeError):
        MEMORY.roster(topology, 4)


def test_restarted_controller_defaults_are_not_a_matched_baseline():
    configuration = {"LinkMetricsRequestIntervalSec": 1, "StatisticsPollingRateSec": 1,
                     "AssocSTALinkMetricsInclusionPolicy": True, "AssocSTATrafficStatsInclusionPolicy": True}
    assert MEMORY.validate_policy(configuration) == configuration
    for name, value in (("LinkMetricsRequestIntervalSec", 60), ("StatisticsPollingRateSec", 10),
                        ("AssocSTALinkMetricsInclusionPolicy", False), ("AssocSTATrafficStatsInclusionPolicy", 1)):
        with pytest.raises(RuntimeError):
            MEMORY.validate_policy(configuration | {name: value})


def test_fronthaul_parser_requires_complete_native_process_set(monkeypatch):
    lines = [f"{100 + index} 8192 /opt/prpl-install-nl80211/bin/beerocks_fronthaul -i wlan{index % 3 * 2}"
             for index in range(15)]
    monkeypatch.setattr(MEMORY, "command", lambda *unused: "\n".join(lines))
    assert len(MEMORY.fronthaul_memory()) == 15
    lines.pop()
    with pytest.raises(RuntimeError, match="fifteen native"):
        MEMORY.fronthaul_memory()


@pytest.mark.parametrize("failure", ["none", "growth", "ceiling", "restart", "missing", "duplicate"])
def test_fronthaul_memory_cannot_hide_a_single_bad_process(failure):
    initial = [{"pid": index + 100, "rss_kib": 10240} for index in range(15)]
    final = [dict(row) for row in initial]
    if failure == "growth":
        final[0]["rss_kib"] += 1025
    if failure == "ceiling":
        initial[0]["rss_kib"] = final[0]["rss_kib"] = 129 * 1024
    if failure == "restart":
        final[0]["pid"] = 999
    if failure == "missing":
        final.pop()
    if failure == "duplicate":
        final[0]["pid"] = final[1]["pid"]
    samples = [{"processes": initial}, {"processes": final}]
    if failure in {"restart", "missing", "duplicate"}:
        with pytest.raises(RuntimeError, match="missing or restarted"):
            MEMORY.evaluate_fronthauls(samples, 1, 128)
    else:
        assert MEMORY.evaluate_fronthauls(samples, 1, 128)["passed"] is (failure == "none")
