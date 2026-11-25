"""
short.py's code lists, held to the codes the engine actually writes.

The engine names every kind of note it puts on an answer in three enums — ProducerDiagnostics.Kind,
ReductionDiagnostics.Kind and DiagnosticNotes.TraversalNote — each kind with the code its note
opens with. This reads those codes out of a published server image (or a jar, or a source
checkout) and fails when:

  - the engine has a code short.py has not decided (in neither SHORT_CODES nor WHOLE_CODES): a new
    kind of note must be a decision, since a battery that does not know it reads it as whole;
  - short.py decides a code the engine no longer writes anywhere: a renamed code would otherwise
    leave a battery checking for words that never come;
  - a typed reason or public warning code short.py relies on is no longer in the engine.

    python3 battery/engine_codes.py --image ghcr.io/embabel/assistant:canary   # main, as merged
    python3 battery/engine_codes.py --image ghcr.io/embabel/assistant:latest --older
    python3 battery/engine_codes.py --jar assistant.jar
    python3 battery/engine_codes.py --source ../assistant      # a checkout of the engine

--image needs docker; --image and --jar need `javap` (any JDK) to read the enums' initialisers.
"""
import argparse
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from short import SHORT_CODES, SHORT_PUBLIC, SHORT_REASONS, WHOLE_CODES  # noqa: E402

ENUMS = {
    "com/embabel/federation/diagnostics/ProducerDiagnostics$Kind.class": "ProducerDiagnostics.Kind",
    "com/embabel/federation/diagnostics/ReductionDiagnostics$Kind.class": "ReductionDiagnostics.Kind",
    "com/embabel/federation/diagnostics/DiagnosticNotes$TraversalNote.class": "DiagnosticNotes.TraversalNote",
}
SOURCES = {
    "ProducerDiagnostics.Kind": "federation/src/main/kotlin/com/embabel/federation/diagnostics/ProducerDiagnostics.kt",
    "ReductionDiagnostics.Kind": "federation/src/main/kotlin/com/embabel/federation/diagnostics/ReductionDiagnostics.kt",
    "DiagnosticNotes.TraversalNote": "federation/src/main/kotlin/com/embabel/federation/diagnostics/DiagnosticNotes.kt",
}


def classes_of(jar_bytes):
    """Every .class in a jar, nested jars (a Spring Boot BOOT-INF/lib) included: path -> bytes."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as z:
        for name in z.namelist():
            if name.endswith(".jar"):
                out.update(classes_of(z.read(name)))
            elif name.endswith(".class"):
                out[name.removeprefix("BOOT-INF/classes/")] = z.read(name)
    return out


def enum_codes_from_class(data):
    """The code each enum constant is built with: the first string its initialiser loads after the name."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "Enum.class")
        open(path, "wb").write(data)
        text = subprocess.run(["javap", "-c", "-p", path], capture_output=True, text=True, check=True).stdout
    init = text.split("static {};", 1)[1]
    codes, strings = set(), []
    for line in init.splitlines():
        m = re.search(r"// String (\S+)$", line)
        if m:
            strings.append(m.group(1))
        elif "putstatic" in line and strings:
            if len(strings) >= 2:
                codes.add(strings[1])
            strings = []
    return codes


def enum_codes_from_source(root, name):
    """The same, read from the Kotlin: `KIND("CODE")`, or a named constant declared in the file."""
    path = os.path.join(root, SOURCES[name])
    text = open(path).read()
    # A code may be a constant of this file or of a neighbour's object (`ExcerptNotes.CODE`).
    consts = {}
    for f in os.listdir(os.path.dirname(path)):
        if f.endswith(".kt"):
            obj = f[:-3]
            for k, v in re.findall(r'const val (\w+)\s*=\s*"([A-Z_]+)"', open(os.path.join(os.path.dirname(path), f)).read()):
                consts.setdefault(k, v)
                consts[obj + "." + k] = v
    # The enum's own block only: its entries end at the first `;` line or the block's closing brace.
    body = re.split(r"^\s*;\s*$|^    }", text.split("enum class " + name.split(".")[-1], 1)[1], maxsplit=1, flags=re.M)[0]
    # Entries, not the comments between them.
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    codes = set()
    for arg in re.findall(r'^\s+[A-Z][A-Z_]*\(\s*("[A-Z_]+"|[A-Za-z_][\w.]*)', body, re.M):
        codes.add(arg.strip('"') if arg.startswith('"') else consts.get(arg, arg))
    return codes


def strings_in(classes):
    """Every code-shaped string constant in the engine's classes, for the codes no enum declares."""
    found = set()
    for data in classes.values():
        found.update(m.decode() for m in re.findall(rb"\b([A-Z][A-Z_]{3,})\b", data))
    return found


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--image")
    g.add_argument("--jar")
    g.add_argument("--source")
    p.add_argument("--older", action="store_true",
                   help="the engine may predate codes short.py knows (a stable release behind main): "
                        "check only that every code it writes is decided")
    a = p.parse_args()

    if a.source:
        engine = {n: enum_codes_from_source(a.source, n) for n in SOURCES}
        everywhere = set()
        for top, _, files in os.walk(a.source):
            if "/src/main/" in top + "/" and "/build/" not in top and "/target/" not in top:
                for f in files:
                    if f.endswith((".kt", ".java")):
                        everywhere.update(re.findall(r"\b([A-Z][A-Z_]{3,})\b", open(os.path.join(top, f), errors="ignore").read()))
        where = a.source
    else:
        if a.image:
            cid = subprocess.run(["docker", "create", a.image], capture_output=True, text=True, check=True).stdout.strip()
            try:
                jar = subprocess.run(["docker", "cp", cid + ":/app/assistant.jar", "-"], capture_output=True, check=True).stdout
            finally:
                subprocess.run(["docker", "rm", cid], capture_output=True)
            # docker cp to stdout is a tar holding the one file.
            import tarfile
            with tarfile.open(fileobj=io.BytesIO(jar)) as t:
                jar = t.extractfile(t.getmembers()[0]).read()
            where = a.image
        else:
            jar = open(a.jar, "rb").read()
            where = a.jar
        classes = classes_of(jar)
        missing = [c for c in ENUMS if c not in classes]
        if missing:
            sys.exit("the engine at %s has no %s: where its notes are named has moved, so this check must too" % (where, missing))
        engine = {ENUMS[c]: enum_codes_from_class(classes[c]) for c in ENUMS}
        everywhere = strings_in(classes)

    bad = 0
    decided = SHORT_CODES | WHOLE_CODES
    declared = set().union(*engine.values())
    for name, codes in sorted(engine.items()):
        print("%-30s %d codes" % (name, len(codes)))
        for code in sorted(codes - decided):
            print("  FAIL %s writes %s, which short.py has not decided: add it to SHORT_CODES or WHOLE_CODES" % (name, code))
            bad += 1
    for code in sorted(decided - declared):
        # Codes written outside the three enums (ranking and aggregate gates, derived-rule inputs,
        # the ask envelope's empty cause) must still be in the engine somewhere.
        if code not in everywhere and not a.older:
            print("  FAIL short.py decides %s, which the engine no longer writes" % code)
            bad += 1
    for code in sorted(SHORT_REASONS | SHORT_PUBLIC):
        if code not in everywhere and not a.older:
            print("  FAIL short.py relies on %s, which the engine no longer has" % code)
            bad += 1
    print("%s: %s" % (where, "every code decided, and every decided code still written" if not bad else "%d problem(s)" % bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
