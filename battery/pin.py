"""
Copy the battery library into a realm, pinned, and check a realm's copy against its pin.

A realm carries its own copy (tests/lib/), so its battery runs with nothing fetched and a change
here never moves a realm's verdicts behind its back. tests/lib/BATTERY records which realm-spec
tag the copy came from and each file's sha256; `check` fails when a file was edited in place or
the pin names a tag whose files differ. Upgrading is `install` again at the newer tag.

    python3 battery/pin.py install ../realm-lago v0.2.2 [short.py short.sh short.mjs]
    python3 battery/pin.py check   ../realm-lago                 # against GitHub, at the pinned tag
    python3 battery/pin.py check   ../realm-lago --spec .        # against a realm-spec checkout

install copies from this checkout, which must be at the tag named: a pin records what was copied.
"""
import hashlib
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("short.py", "short.sh", "short.mjs")
RAW = "https://raw.githubusercontent.com/embabel-worlds/realm-spec/%s/battery/%s"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_pin(realm):
    lines = [l.split() for l in open(os.path.join(realm, "tests", "lib", "BATTERY")) if l.strip() and not l.startswith("#")]
    tag = next(v for k, v, *_ in lines if k == "realm-spec")
    return tag, {k: v for k, v, *_ in lines if k in FILES}


def install(realm, tag, files):
    head = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    at = subprocess.run(["git", "-C", HERE, "rev-parse", tag + "^{commit}"], capture_output=True, text=True).stdout.strip()
    if at != head:
        sys.exit("this checkout is not at %s; check it out first, so the pin records what is copied" % tag)
    lib = os.path.join(realm, "tests", "lib")
    os.makedirs(lib, exist_ok=True)
    pin = ["# The battery library, copied from embabel-worlds/realm-spec battery/ at the tag below.",
           "# Do not edit these files here: change realm-spec, then `python3 battery/pin.py install`.",
           "realm-spec " + tag]
    for f in files:
        data = open(os.path.join(HERE, f), "rb").read()
        open(os.path.join(lib, f), "wb").write(data)
        pin.append("%s %s" % (f, sha(data)))
    open(os.path.join(lib, "BATTERY"), "w").write("\n".join(pin) + "\n")
    print("pinned %s at realm-spec %s: %s" % (realm, tag, ", ".join(files)))


def check(realm, spec=None):
    tag, pinned = read_pin(realm)
    bad = 0
    for f, want in sorted(pinned.items()):
        local = open(os.path.join(realm, "tests", "lib", f), "rb").read()
        if sha(local) != want:
            print("FAIL %s: tests/lib/%s was edited in place (its sha256 is not the pin's)" % (realm, f)); bad += 1
        if spec:
            upstream = subprocess.run(["git", "-C", spec, "show", "%s:battery/%s" % (tag, f)], capture_output=True, check=True).stdout
        else:
            upstream = urllib.request.urlopen(RAW % (tag, f)).read()
        if sha(upstream) != want:
            print("FAIL %s: tests/lib/%s is not realm-spec %s's battery/%s" % (realm, f, tag, f)); bad += 1
    print("%s: %s" % (realm, "the battery library is realm-spec %s, unedited (%s)" % (tag, ", ".join(sorted(pinned))) if not bad else "%d problem(s)" % bad))
    return bad


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "install":
        install(sys.argv[2], sys.argv[3], sys.argv[4:] or list(FILES))
    elif len(sys.argv) >= 3 and sys.argv[1] == "check":
        spec = sys.argv[sys.argv.index("--spec") + 1] if "--spec" in sys.argv else None
        sys.exit(1 if check(sys.argv[2], spec) else 0)
    else:
        sys.exit(__doc__)
