# -*- coding: utf-8 -*-
"""How the audio path does on real people, not synthetic voices.

    python api/scripts/eval_natural_audio.py [--fetch] [--include-unverified]

`--fetch` downloads the clips into storage/natural (gitignored: none of this is
redistributed). Each clip goes through the same `transcribe_detecting` the upload
pipeline uses, and is scored against the human transcript where one exists.

By default only audio with a stated open licence is used: AMI meetings (CC-BY-4.0)
and Common Voice Urdu through a CC-BY-4.0 collection. `--include-unverified` adds
sets whose licence is unstated or unknown, which are closer to real conversation but
must not be redistributed or relied on for anything published. See docs/TEST_AUDIO.md.

This calls the configured transcription provider and costs real credit, which is
why it is a script and not part of the test suite.

Word error rate is computed after normalising, so punctuation and case are not
counted as errors. It is still a rough number across scripts: a transcript in
Nastaliq scored against one in Nastaliq means something, one in Devanagari does not,
so a clip with no usable reference reports only what it can.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import re
import subprocess
import sys
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))

from salix.config import get_settings  # noqa: E402
from salix.pipeline.language import _shares, transcribe_detecting  # noqa: E402
from salix.providers.deepgram_asr import DeepgramASR  # noqa: E402

ROOT = API_DIR.parent / "storage" / "natural"
NEXDATA = (
    "https://huggingface.co/datasets/Nexdata-AI/"
    "352-Hours-Urdu-Full-Duplex-Spontaneous-Dialogue-Smartphone-speech-Data-Sample/resolve/main"
)
AMI_ROWS = (
    "https://datasets-server.huggingface.co/rows?dataset=edinburghcstr%2Fami"
    "&config=ihm&split=test&offset={offset}&length=100"
)
UNIFIED_URDU = "https://huggingface.co/datasets/abidanoaman/unified-urdu-speech-asr/resolve/main/test"
CSALT_ROWS = (
    "https://datasets-server.huggingface.co/rows?dataset=urdu-asr%2Fcsalt-voice"
    "&config=default&split=validation&offset={offset}&length=1"
)


@dataclass
class Clip:
    name: str
    expected: str
    path: Path
    reference: str = ""
    source: str = ""
    licence: str = "unknown"


def _download(url: str, target: Path) -> None:
    if target.exists():
        return
    print(f"  fetching {target.name}")
    request = urllib.request.Request(url, headers={"User-Agent": "salix-eval"})
    with urllib.request.urlopen(request, timeout=300) as response:
        target.write_bytes(response.read())


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "salix-eval"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def fetch() -> None:
    """Audio with a stated open licence."""
    ROOT.mkdir(parents=True, exist_ok=True)

    # The longest utterances out of a stretch of real meetings: a one-word "yeah"
    # scores 0% or 100% and says nothing.
    if not list(ROOT.glob("ami_clip_*.json")):
        rows = [r["row"] for r in _get_json(AMI_ROWS.format(offset=300))["rows"]]
        rows.sort(key=lambda r: -len(r["text"]))
        for index, row in enumerate(rows[:6]):
            _download(row["audio"][0]["src"], ROOT / f"ami_clip_{index}.wav")
            (ROOT / f"ami_clip_{index}.json").write_text(
                json.dumps({"text": row["text"], "meeting": row["meeting_id"]}), encoding="utf-8"
            )

    if not list(ROOT.glob("cv_ur_*.json")):
        request = urllib.request.Request(f"{UNIFIED_URDU}/metadata.csv", headers={"User-Agent": "salix-eval"})
        with urllib.request.urlopen(request, timeout=120) as response:
            table = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
        voices = [r for r in table if r["source"] == "CommonVoice"][:6]
        for index, row in enumerate(voices):
            _download(f"{UNIFIED_URDU}/{row['audio']}", ROOT / f"cv_ur_{index}.wav")
            (ROOT / f"cv_ur_{index}.json").write_text(
                json.dumps({"text": row["transcript"]}, ensure_ascii=False), encoding="utf-8"
            )


def fetch_unverified() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for suffix in ("wav", "txt", "metadata"):
        _download(f"{NEXDATA}/0231_001_O1.{suffix}", ROOT / f"nexdata_0231.{suffix}")

    for offset in (0, 60, 120, 180, 240):
        meta = ROOT / f"csalt_{offset}.json"
        if not meta.exists():
            request = urllib.request.Request(
                CSALT_ROWS.format(offset=offset), headers={"User-Agent": "salix-eval"}
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                row = json.load(response)["rows"][0]["row"]
            meta.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            _download(row["audio"][0]["src"], ROOT / f"csalt_{offset}.wav")


def _trim(source: Path, minutes: float) -> Path:
    """Long recordings are cut, because transcription is billed by the minute."""
    out = ROOT / f"{source.stem}_{int(minutes)}m.mp3"
    if not out.exists():
        ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-t", str(minutes * 60),
             "-ac", "1", "-ar", "16000", str(out)],
            check=True,
        )
    return out


def _reference_from_timed(text: str) -> str:
    """Strip speaker labels and timestamps from a transcript file."""
    keep = []
    for line in text.splitlines():
        line = re.sub(r"^\s*\[[^\]]*\]\s*", "", line)
        line = re.sub(r"^\s*(\d+(\.\d+)?[\s,\-]+)+", "", line)
        line = re.sub(r"^\s*[A-Za-z_ ]{1,20}:\s*", "", line)
        if line.strip() and not set(line.strip()) <= {"="} and not line.startswith("Conversation"):
            keep.append(line)
    return " ".join(keep)


def _nexdata_reference(minutes: float) -> str:
    """Tab-separated start, end, speaker, text; only what the trimmed clip covers."""
    lines = (ROOT / "nexdata_0231.txt").read_text(encoding="utf-8").splitlines()
    rows = [line.split("\t") for line in lines]
    return " ".join(row[3] for row in rows if len(row) >= 4 and float(row[0]) < minutes * 60)


def clips(minutes: float, unverified: bool = False) -> list[Clip]:
    found: list[Clip] = []
    for meta in sorted(ROOT.glob("ami_clip_*.json")):
        found.append(
            Clip(
                f"English meeting speech ({meta.stem})", "en", meta.with_suffix(".wav"),
                reference=json.loads(meta.read_text(encoding="utf-8"))["text"],
                source="AMI", licence="CC-BY-4.0",
            )
        )
    for meta in sorted(ROOT.glob("cv_ur_*.json")):
        found.append(
            Clip(
                f"Urdu volunteer voice ({meta.stem})", "ur", meta.with_suffix(".wav"),
                reference=json.loads(meta.read_text(encoding="utf-8"))["text"],
                source="Common Voice", licence="CC-BY-4.0",
            )
        )
    if not unverified:
        return found

    nexdata = ROOT / "nexdata_0231.wav"
    if nexdata.exists():
        found.append(
            Clip(
                "Urdu spontaneous dialogue (Nexdata sample)", "ur",
                _trim(nexdata, minutes),
                reference=_nexdata_reference(minutes),
                source="spontaneous, smartphone",
            )
        )
    for meta in sorted(ROOT.glob("csalt_*.json")):
        row = json.loads(meta.read_text(encoding="utf-8"))
        found.append(
            Clip(
                f"Urdu natural voice ({meta.stem})", "ur",
                meta.with_suffix(".wav"),
                reference=row.get("raw_transcription") or row.get("transcription") or "",
                source="CSALT voice",
            )
        )
    real = API_DIR.parent / "storage" / "samples" / "real"
    sales = real / "sales_en_1.wav"
    if sales.exists():
        found.append(Clip("English sales conversation", "en", _trim(sales, minutes), source="local"))
    ami = real / "ami_ES2002a.wav"
    if ami.exists():
        found.append(Clip("English AMI meeting ES2002a", "en", _trim(ami, minutes), source="AMI CC-BY-4.0"))
    return found


def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).casefold()
    # Spellings Urdu writers treat as one word: alef with or without madda or
    # hamza, and the Arabic and Urdu forms of yeh and kaf. Nobody hears a difference.
    text = re.sub("[آأإ]", "ا", text)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return text.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = _words(reference), _words(hypothesis)
    if not ref:
        return float("nan")
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--minutes", type=float, default=8)
    parser.add_argument("--include-unverified", action="store_true")
    args = parser.parse_args()

    if args.fetch:
        fetch()
        if args.include_unverified:
            fetch_unverified()

    settings = get_settings()
    if not settings.deepgram_api_key:
        print("No transcription key configured; nothing can be measured.")
        return 1

    providers = SimpleNamespace(asr=DeepgramASR(settings))
    correct = total = 0
    rates: dict[str, list[float]] = {}
    for clip in clips(args.minutes, args.include_unverified):
        try:
            asr, language = await transcribe_detecting(providers, str(clip.path))
        except Exception as exc:  # noqa: BLE001
            print(f"{clip.name}: ERROR {exc}")
            continue
        text = " ".join(s.text for s in asr.sentences)
        devanagari, arabic = _shares(asr.sentences)
        speakers = len({s.speaker_id for s in asr.sentences})
        hit = language == clip.expected
        correct += hit
        total += 1
        wer = f"{word_error_rate(clip.reference, text):.0%}" if clip.reference else "no reference"
        if clip.reference:
            rates.setdefault(clip.expected, []).append(word_error_rate(clip.reference, text))
        print(
            f"{'ok  ' if hit else 'MISS'} [{clip.licence}] {clip.name}: expected={clip.expected} got={language} "
            f"wer={wer} speakers={speakers} lines={len(asr.sentences)} "
            f"devanagari={devanagari:.2f} arabic={arabic:.2f} seconds={asr.duration_ms // 1000}"
        )
        sys.stdout.buffer.write(("     " + text[:160] + "\n").encode("utf-8"))
        sys.stdout.flush()
    print(f"\nlanguage correct: {correct}/{total}")
    for language, values in rates.items():
        print(f"mean word error, {language}: {sum(values) / len(values):.0%} over {len(values)} clip(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
