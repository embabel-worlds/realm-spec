"""
The three copies of the verdict (short.py, short.mjs, short.sh) give the same answer on every
answer in canned/, and that answer is the one expected.json records. Run from anywhere:

    python3 battery/test_short.py

A change to what counts as short is a change to expected.json in the same commit, so the
difference is on the record. Needs python3, node and /bin/sh; nothing reaches the network.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from short import figure_of, short  # noqa: E402

canned = sorted(f[:-5] for f in os.listdir(os.path.join(HERE, "canned")) if f.endswith(".json"))
expected = json.load(open(os.path.join(HERE, "expected.json")))
answers = {k: open(os.path.join(HERE, "canned", k + ".json")).read() for k in canned}
bad = 0


def same(where, name, got, want):
    global bad
    if got != want:
        print("FAIL %-6s %s: got %r, want %r" % (where, name, got, want))
        bad += 1


if sorted(expected) != canned:
    print("FAIL expected.json and canned/ name different answers: %s" % sorted(set(expected) ^ set(canned)))
    bad += 1

for k in canned:
    same("python", k, short(json.loads(answers[k]), 7), expected.get(k))

node = """
import { short } from %s
import { readFileSync } from 'node:fs'
const names = JSON.parse(process.argv[1])
const out = {}
for (const k of names) out[k] = short(JSON.parse(readFileSync(%s + '/canned/' + k + '.json', 'utf8')), 7)
console.log(JSON.stringify(out))
""" % (json.dumps("file://" + os.path.join(HERE, "short.mjs")), json.dumps(HERE))
js = json.loads(subprocess.run(["node", "--input-type=module", "-e", node, json.dumps(canned)],
                               capture_output=True, text=True, check=True).stdout)
for k in canned:
    same("js", k, js[k], expected.get(k))

# The code lists themselves, so a code added to one copy alone is caught before any answer uses it.
lists = """
import * as s from %s
console.log(JSON.stringify({codes: [...s.SHORT_CODES].sort(), reasons: [...s.SHORT_REASONS].sort(), public: [...s.SHORT_PUBLIC].sort()}))
""" % json.dumps("file://" + os.path.join(HERE, "short.mjs"))
from short import SHORT_CODES, SHORT_PUBLIC, SHORT_REASONS  # noqa: E402
jl = json.loads(subprocess.run(["node", "--input-type=module", "-e", lists], capture_output=True, text=True, check=True).stdout)
same("lists", "SHORT_CODES", jl["codes"], sorted(SHORT_CODES))
same("lists", "SHORT_REASONS", jl["reasons"], sorted(SHORT_REASONS))
same("lists", "SHORT_PUBLIC", jl["public"], sorted(SHORT_PUBLIC))

# The shell helpers: short_of is the verdict alone, and n / rows put the figure in its place.
sh = 'SHORT_PY_FILE="$1/short.py" . "$1/short.sh"; shift; for f; do short_of "$(cat "$f")"; echo; done'
lines = subprocess.run(["sh", "-c", sh, "sh", HERE] + [os.path.join(HERE, "canned", k + ".json") for k in canned],
                       capture_output=True, text=True, check=True).stdout.split("\n")
for k, line in zip(canned, lines):
    want = expected.get(k)
    same("sh", k, line or None, None if want is None else short(json.loads(answers[k])))

figure = 'SHORT_PY_FILE="$1/short.py" . "$1/short.sh"; shift; for f; do a=$(cat "$f"); case "$a" in *\\"outcome\\"*) rows "$a" ;; *) n "$a" ;; esac; done'
lines = subprocess.run(["sh", "-c", figure, "sh", HERE] + [os.path.join(HERE, "canned", k + ".json") for k in canned],
                       capture_output=True, text=True, check=True).stdout.splitlines()
for k, line in zip(canned, lines):
    d = json.loads(answers[k])
    v = figure_of(d)
    same("sh-fig", k, line, short(d, v) or str(v))

# The file run as a script prints the same line a battery's n() would.
for k in canned:
    d = json.loads(answers[k])
    v = figure_of(d)
    out = subprocess.run([sys.executable, os.path.join(HERE, "short.py")], input=answers[k],
                         capture_output=True, text=True, check=True).stdout.strip()
    same("cli", k, out, short(d, v) or str(v))

print("%d answers, %s" % (len(canned), "all four forms agree" if not bad else "%d disagreement(s)" % bad))
sys.exit(1 if bad else 0)
