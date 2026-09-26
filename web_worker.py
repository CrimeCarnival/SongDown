"""One isolated converter process per web job. Only emits structured events."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

from audio_converter_core import ConversionOptions, run_conversion


def emit(kind, value):
    print(json.dumps({"kind": kind, "value": value}, ensure_ascii=False), flush=True)


def main():
    root = Path(sys.argv[1]).resolve()
    settings = json.loads((root / "request.json").read_text(encoding="utf-8"))
    tasks = settings["tasks"]
    options = ConversionOptions(
        root / "input", root / "output", convert_ncm="ncm" in tasks,
        convert_ogg="ogg" in tasks, convert_mgg="mgg" in tasks,
        convert_mflac="mflac" in tasks, copy_lrc="lrc" in tasks,
    )
    stats = run_conversion(options, log=lambda s: emit("log", s),
                           progress=lambda s: emit("stats", asdict(s)))
    emit("done", asdict(stats))
    return 0 if not stats.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
