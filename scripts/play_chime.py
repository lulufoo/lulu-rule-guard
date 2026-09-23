#!/usr/bin/env python3
"""stop hook — agent completion chime (macOS). Settings from rule-guard-config.json."""
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config_util import ChimeSettings, load_config

CHIME_FFMPEG = Path("/opt/homebrew/bin/ffmpeg")
CHIME_DEBUG = False


def _log_debug(project_root: Path, message: str) -> None:
    if not CHIME_DEBUG:
        return
    log_path = project_root / ".cache" / "cursor-chime.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")


def _find_ffmpeg() -> Optional[str]:
    if CHIME_FFMPEG.is_file():
        return str(CHIME_FFMPEG)
    for candidate in ("ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        found = shutil.which(candidate)
        if found:
            return found
        p = Path(candidate)
        if p.is_file():
            return str(p)
    return None


def _afplay_volume_arg(volume: Any) -> str:
    try:
        v = float(volume)
    except (TypeError, ValueError):
        v = 1.0
    return str(max(0.0, min(v, 1.0)))


def _ffmpeg_gain(gain: Any) -> int:
    try:
        g = int(gain)
    except (TypeError, ValueError):
        g = 25
    return max(0, g)


def _audio_filter(gain: int) -> str:
    return (
        f"volume={gain},alimiter=limit=0.99:attack=1:release=50,"
        "loudnorm=I=-12:TP=-0.5:LRA=5"
    )


def _play_chime(project_root: Path, chime: ChimeSettings) -> None:
    sound = Path(chime.sound).expanduser()
    volume = _afplay_volume_arg(chime.volume)
    gain = _ffmpeg_gain(chime.gain)
    audio_filter = _audio_filter(gain)

    if not sound.is_file():
        _log_debug(project_root, f"missing chime file: {sound}")
        return

    ffmpeg_bin = _find_ffmpeg()
    if ffmpeg_bin:
        tmp = tempfile.mkstemp(prefix="cursor-chime.", suffix="")[1]
        wav_path = f"{tmp}.wav"
        _log_debug(
            project_root,
            f"play ffmpeg gain={gain} volume={volume} file={sound}",
        )
        subprocess.run(
            [
                ffmpeg_bin,
                "-loglevel",
                "quiet",
                "-y",
                "-i",
                str(sound),
                "-filter:a",
                audio_filter,
                wav_path,
            ],
            check=False,
            capture_output=True,
        )
        subprocess.run(["afplay", "-v", volume, wav_path], check=False)
        Path(wav_path).unlink(missing_ok=True)
    else:
        _log_debug(
            project_root,
            f"play afplay volume={volume} file={sound}",
        )
        subprocess.run(["afplay", "-v", volume, str(sound)], check=False)


def main() -> int:
    import argparse
    import select

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--platform", default="copilot")
    args, _ = parser.parse_known_args()

    cfg = load_config(args.platform)
    if not cfg.chime.enabled:
        return 0

    project_root = Path.cwd()

    payload: dict = {}
    if not sys.stdin.isatty():
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 1.0)
            if ready:
                raw = sys.stdin.buffer.read1(65536).decode("utf-8", errors="replace")
                payload = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError, ValueError):
            payload = {}

    if args.platform == "cursor" and payload.get("status") != "completed":
        return 0

    _play_chime(project_root, cfg.chime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
