"""Stand-in for ``whisper-cli`` (stdlib only), steered through environment.

FAKE_WCPP_LOG      append one JSON line with argv and the working directory
FAKE_WCPP_PAYLOAD  JSON file to write verbatim as the result
FAKE_WCPP_MODE     fail | nojson | sleep (writes FAKE_WCPP_PID, then blocks)
FAKE_WCPP_HELP     "old" prints a usage without the modern flags
"""

import json
import os
import sys
import time

args = sys.argv[1:]
log = os.environ.get("FAKE_WCPP_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": args, "cwd": os.getcwd()}) + "\n")

if "--help" in args:
    if os.environ.get("FAKE_WCPP_HELP") == "old":
        print("usage: main [options] file0\n  -m FNAME, --model FNAME", file=sys.stderr)
    else:
        print(
            "whisper-cli version: 1.7.4\n"
            "  -m FNAME, --model FNAME\n  -f FNAME, --file FNAME\n"
            "  -l LANG, --language LANG\n  -ojf, --output-json-full\n"
            "  -of FNAME, --output-file FNAME\n  -ng, --no-gpu\n"
            "  -np, --no-prints\n  -ot N, --offset-t N\n  -d N, --duration N",
            file=sys.stderr,
        )
    sys.exit(0)

mode = os.environ.get("FAKE_WCPP_MODE")
if mode == "fail":
    sys.exit(3)
if mode == "sleep":
    with open(os.environ["FAKE_WCPP_PID"], "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    time.sleep(60)
    sys.exit(0)
if mode == "nojson":
    sys.exit(0)

payload = os.environ.get("FAKE_WCPP_PAYLOAD")
if payload:
    with open(payload, encoding="utf-8") as source:
        body = source.read()
else:
    body = json.dumps(
        {
            "result": {"language": "es"},
            "transcription": [
                {"offsets": {"from": 0, "to": 100}, "text": "hola"},
                {"offsets": {"from": 100, "to": 250}, "text": " mundo"},
            ],
        }
    )
base = args[args.index("--output-file") + 1]
with open(base + ".json", "w", encoding="utf-8") as handle:
    handle.write(body)
