#!/bin/sh
# Run one preregistered stage; never retry or bypass a failed prior gate.
set -u
E=$(cd "$(dirname "$0")" && pwd)
ROOT="/hive-cache/codeagent/home/enginescope-sglang-causal-replay-2026-11-04"
N=$1
SCENARIO=${SCENARIO:-$N}
case "$SCENARIO" in sequence-smoke|history-16k|bridge-32k|historical-pair-32k) ;; *) exit 92;; esac
case "$N" in "$SCENARIO"|"$SCENARIO"-*) ;; *) exit 92;; esac
/usr/bin/grep -Eq "^[0-9a-f]{64}  ${SCENARIO}[.]toml$" "$E/IDENTITIES.sha256" || exit 92
ALSO_NAME=${3-}
L="$E/logs"
mkdir -p "$L"
cd "$E" || exit 93
[ -f IDENTITIES.sha256 ] && [ -f IDENTITIES.private.sha256 ] || { echo 'missing identity manifests' >&2; exit 92; }
shasum -c IDENTITIES.sha256 || exit 92
sudo -n -u codeagent shasum -c IDENTITIES.private.sha256 || exit 92
if [ "$#" -ge 2 ]; then
  /opt/local/bin/python3.14 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["stage_gate"]["status"] == "pass" else 1)' "$E/$2.json" || exit 92
fi
sudo -n -u codeagent /usr/bin/true || exit 92
listeners=$(netstat -an -p tcp) || exit 92
if printf '%s\n' "$listeners" | /usr/bin/grep -Eq '[.]14172[[:space:]].*LISTEN'; then echo 'port 14172 busy' >&2; exit 90; fi
sudo -n -u codeagent /bin/sh -c 'if [ -e "$1" ] || [ -L "$1" ]; then exit 10; fi' sh "$ROOT/$N"
exists=$?
[ "$exists" -eq 0 ] || { [ "$exists" -eq 10 ] && exit 91; exit 92; }
host() {
  date -u
  memory_pressure
  sysctl vm.swapusage
  vm_stat
  df -k "$ROOT"
}
pressure_ok() { memory_pressure | /usr/bin/awk '/free percentage/ {gsub(/%/, "", $NF); if ($NF+0 >= 13) ok=1} END {exit !ok}'; }
swapouts() { vm_stat | /usr/bin/awk '/^Swapouts/ {gsub(/\./, "", $2); print $2; found=1} END {if (!found) exit 1}'; }
host > "$L/$N.pre-host.txt" || exit 92
pressure_ok || exit 92
free=$(df -k "$ROOT" | /usr/bin/awk 'NR==2 {print $4}')
[ -n "$free" ] && [ "$free" -ge 20971520 ] || exit 92
pre_swap=$(swapouts) || exit 92
"$E/es.sh" doctor > "$L/$N.doctor.txt" 2>&1 || exit 92
"$E/es.sh" plan "$E/$SCENARIO.toml" > "$L/$N.plan.json" 2> "$L/$N.plan.stderr" || exit 92
"$E/es.sh" run "$E/$SCENARIO.toml" --out "$ROOT/$N" > "$L/$N.stdout" 2> "$L/$N.stderr"
rc=$?
echo "exit=$rc" > "$L/$N.exit"
host > "$L/$N.post-host.txt"
post_swap=$(swapouts) || post_swap=unknown
"$E/harvest.sh" "$N" > "$L/$N.harvest.txt" 2>&1 || { echo 'harvest failed' >&2; exit 94; }
[ "$pre_swap" = "$post_swap" ] || { echo 'swapouts changed' >&2; exit 95; }
pressure_ok || exit 95
"$E/es.sh" compare "$ROOT/$N" --json > "$L/$N.compare.json" 2> "$L/$N.compare.stderr"
[ -d "$E/runs/$N/cells" ] || { echo 'missing harvested cells' >&2; [ "$rc" -ne 0 ] && exit "$rc"; exit 3; }
set -- live --run "$E/runs/$N" --inventory "$L/$N.raw-sha256.txt" --out "$E/$N" --plan "$L/$N.plan.json" --fixtures-summary "$E/FIXTURES_SUMMARY.json"
[ -z "$ALSO_NAME" ] || set -- "$@" --also "$E/runs/$ALSO_NAME:$L/$ALSO_NAME.raw-sha256.txt"
[ "${FINAL_STAGE-0}" != 1 ] || set -- "$@" --final-stage
/opt/local/bin/python3.14 "$E/causal_report.py" "$@" > "$L/$N.live.stdout" 2> "$L/$N.live.stderr"
live=$?
echo "live=$live" >> "$L/$N.exit"
[ "$rc" -eq 0 ] || exit "$rc"
exit "$live"
