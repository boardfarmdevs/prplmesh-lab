#!/usr/bin/env python3
import json
import os
import subprocess


OBJECT = "X_PRPLWARE-COM_Controller.Configuration"


def call(method, payload):
    result = subprocess.run(
        ["ubus", "-t", "5", "call", OBJECT, method, json.dumps(payload)],
        check=True, capture_output=True, text=True, timeout=8,
    )
    return json.JSONDecoder().raw_decode(result.stdout.lstrip())[0]


def policy(interval=1):
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 60:
        raise ValueError("metrics interval must be an integer from 1 to 60 seconds")
    return {
        "LinkMetricsRequestIntervalSec": interval,
        "StatisticsPollingRateSec": interval,
        "AssocSTALinkMetricsInclusionPolicy": True,
        "AssocSTATrafficStatsInclusionPolicy": True,
    }


def configure(interval=1):
    parameters = policy(interval)
    call("_set", {"parameters": parameters})
    observed = call("_get", {"rel_path": "", "depth": 0}).get(OBJECT + ".", {})
    if any(observed.get(key) != value for key, value in parameters.items()):
        raise RuntimeError("native controller did not apply the requested metrics policy")
    return parameters


if __name__ == "__main__":
    interval = int(os.environ.get("PRPL_METRICS_INTERVAL_SEC", "1"))
    result = configure(interval)
    print(json.dumps(result, sort_keys=True))
