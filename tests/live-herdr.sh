#!/usr/bin/env bash
# Explicitly opt-in control-plane smoke. No Pi, primary home, or model is used.
set -euo pipefail
if [[ ${FMVOICE_LIVE_HERDR:-0} != 1 ]]; then
  echo 'SKIP: set FMVOICE_LIVE_HERDR=1 and HERDR_LAB_HELPER to run the isolated smoke'
  exit 0
fi
: "${HERDR_LAB_HELPER:?Set the path to the authorized fm-herdr-lab.sh helper}"
HERDR_LAB_SESSION=$("$HERDR_LAB_HELPER" name fase2-job-manager-cli)
trap '"$HERDR_LAB_HELPER" teardown "$HERDR_LAB_SESSION"' EXIT
"$HERDR_LAB_HELPER" provision "$HERDR_LAB_SESSION"
"$HERDR_LAB_HELPER" run "$HERDR_LAB_SESSION" status --json | python3 -c '
import json,sys
value=json.load(sys.stdin)
assert value["server"]["running"]
assert value["client"]["session"].startswith("fm-lab-")
assert value["client"]["session"] != "default"
print("Isolated Herdr session is healthy")'
"$HERDR_LAB_HELPER" run "$HERDR_LAB_SESSION" api schema --json | python3 -c '
import json,sys
schema=json.load(sys.stdin)
def walk(value):
    if isinstance(value,dict):
        if "const" in value: yield value["const"]
        for child in value.values(): yield from walk(child)
    elif isinstance(value,list):
        for child in value: yield from walk(child)
methods=list(walk(schema))
assert "agent.get" in methods
assert "agent.send_keys" in methods
defs=schema["schemas"]["request"]["$defs"]
assert defs["AgentSendKeysParams"]["properties"]["keys"]["type"] == "array"
print("Real agent.get and agent.send_keys contracts verified")'
