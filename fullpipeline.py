"""
Hold-to-record Russian ASR + Local LLM Tutor (Windows)
- Hold 'a' to record from your mic
- Release 'a' to:
  1) save audio -> mp3
  2) Whisper transcribe (RU)
  3) send RU text to local Ollama LLM
  4) print: transcript + EN translation + gloss + grammar notes + alternatives

Install:
  pip install sounddevice soundfile numpy openai-whisper pynput

Requires:
  - FFmpeg in PATH (for WAV -> MP3)
  - Ollama installed and working in CMD:
      ollama --version
  - Model pulled in Ollama (example):
      ollama pull qwen2.5:7b
"""

from __future__ import annotations

import sys
import time
import queue
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard
import whisper


# ----------------------------
# Config
# ----------------------------
WHISPER_MODEL_NAME = "large"     # base/small/medium/large
WHISPER_LANGUAGE = "ru"
SAMPLE_RATE = 16000              # good for BT hands-free mics
CHANNELS = 1
KEY_TO_RECORD = keyboard.KeyCode.from_char('a')

INPUT_DEVICE_INDEX = 24          # your mic device index
STREAM_LATENCY = "low"           # helps responsiveness

OUT_DIR = Path("./recordings")
OUT_DIR.mkdir(exist_ok=True)

KEEP_WAV = True

# Ollama
OLLAMA_MODEL = "qwen2.5:7b"      # change if you pulled a different one
OLLAMA_TIMEOUT_SEC = 180         # large models can take longer


PROMPT_TEMPLATE = """You are a Russian→English translation tutor.
For the Russian text below, output:

Natural English translation

Word-by-word gloss (tokenized)

Grammar notes: cases, aspect, tense, gender/number, syntax/word order

2 alternative English phrasings and why

Russian: «{russian}»
"""


# ----------------------------
# Recorder
# ----------------------------
@dataclass
class RecordingState:
    recording: bool = False
    started_at: float = 0.0
    frames: list[np.ndarray] = None

    def __post_init__(self):
        self.frames = []


class HoldToRecordASR:
    def __init__(self):
        self.state = RecordingState()
        self.audio_q: "queue.Queue[np.ndarray]" = queue.Queue()
        self.stream: sd.InputStream | None = None
        self.listener: keyboard.Listener | None = None

        print(f"[info] Loading Whisper model: {WHISPER_MODEL_NAME} ...")
        self.whisper_model = whisper.load_model(WHISPER_MODEL_NAME)

        if shutil.which("ffmpeg") is None:
            print("[warn] FFmpeg not found on PATH. MP3 conversion will fail.")

        if shutil.which("ollama") is None:
            print("[warn] Ollama not found on PATH. LLM step will fail.")
            print("       Run: where ollama")

        print("\nControls:")
        print("  - Hold 'a' to record")
        print("  - Release 'a' to transcribe + translate")
        print("  - Press ESC to quit\n")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}", file=sys.stderr)
        if self.state.recording:
            self.audio_q.put(indata.copy())

    def start_stream(self):
        # NOTE: if you still get BT takeover problems, you can switch to
        # opening/closing the stream only while recording.
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            device=INPUT_DEVICE_INDEX,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=0,
            latency=STREAM_LATENCY,
        )
        self.stream.start()

    def stop_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
            except Exception:
                pass
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _drain_queue_into_frames(self):
        while not self.audio_q.empty():
            try:
                self.state.frames.append(self.audio_q.get_nowait())
            except queue.Empty:
                break

    def _save_wav(self, audio: np.ndarray) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        wav_path = OUT_DIR / f"rec_{ts}.wav"
        sf.write(wav_path, audio, SAMPLE_RATE, subtype="PCM_16")
        return wav_path

    def _wav_to_mp3(self, wav_path: Path) -> Path:
        mp3_path = wav_path.with_suffix(".mp3")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(wav_path),
            "-codec:a", "libmp3lame",
            "-q:a", "2",
            str(mp3_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{proc.stderr}")
        return mp3_path

    def _transcribe_with_whisper(self, audio_path: Path) -> str:
        result = self.whisper_model.transcribe(
            str(audio_path),
            language=WHISPER_LANGUAGE,
            task="transcribe",
            fp16=False,      # safe for CPU; if torch+CUDA configured, you can set True
            verbose=False,
        )
        return (result.get("text") or "").strip()

    def _run_ollama(self, russian_text: str) -> str:
        prompt = PROMPT_TEMPLATE.format(russian=russian_text)

        proc = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL],
            input=prompt,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            timeout=OLLAMA_TIMEOUT_SEC,
        )

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or "(no stderr)"
            raise RuntimeError(f"Ollama error (code {proc.returncode}):\n{stderr}")

        return proc.stdout.strip()

    def _sanitize_transcript(self, text: str) -> str:
        # Whisper sometimes returns leading/trailing quotes/spaces; keep it simple.
        return " ".join(text.strip().split())

    def on_press(self, key):
        if key == keyboard.Key.esc:
            print("\n[info] Exiting...")
            return False

        if key == KEY_TO_RECORD and not self.state.recording:
            self.state.recording = True
            self.state.started_at = time.time()
            self.state.frames = []
            print("[rec] Recording... (hold 'a')")

    def on_release(self, key):
        if key == KEY_TO_RECORD and self.state.recording:
            self.state.recording = False

            # Collect any remaining queued frames
            self._drain_queue_into_frames()

            if not self.state.frames:
                print("[rec] No audio captured.")
                return

            audio = np.concatenate(self.state.frames, axis=0).reshape(-1)
            duration = len(audio) / SAMPLE_RATE
            if duration < 0.15:
                print(f"[rec] Too short ({duration:.2f}s). Try again.")
                return

            try:
                wav_path = self._save_wav(audio)
                mp3_path = self._wav_to_mp3(wav_path)

                if not KEEP_WAV:
                    try:
                        wav_path.unlink(missing_ok=True)
                    except Exception:
                        pass

                print(f"[asr] Transcribing ({duration:.2f}s) ...")
                ru_text = self._sanitize_transcript(self._transcribe_with_whisper(mp3_path))

                print("\n=== RUSSIAN TRANSCRIPT ===")
                print(ru_text if ru_text else "(no text detected)")
                print("==========================\n")

                if not ru_text:
                    return

                print(f"[llm] Translating + explaining with {OLLAMA_MODEL} ...")
                tutor = self._run_ollama(ru_text)

                print("\n=== TUTOR OUTPUT ===")
                print(tutor)
                print("====================\n")

            except subprocess.TimeoutExpired:
                print(f"[error] Ollama timed out after {OLLAMA_TIMEOUT_SEC}s.", file=sys.stderr)
            except Exception as e:
                print(f"[error] {e}", file=sys.stderr)

    def run(self):
        self.start_stream()
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()
        self.listener.join()
        self.stop_stream()


if __name__ == "__main__":
    HoldToRecordASR().run()
