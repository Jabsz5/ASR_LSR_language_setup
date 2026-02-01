"""
Hold-to-record Russian ASR (Windows)
- Hold 'a' to record from your default mic
- On release, saves recording, converts to MP3, runs Whisper, prints transcript

Install:
  pip install sounddevice soundfile numpy openai-whisper pynput

Requires:
  - FFmpeg in PATH (for WAV -> MP3). If you already installed it for Whisper, you're good.
"""

from __future__ import annotations

import os
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
MODEL_NAME = "large"          # try: base, small, medium
LANGUAGE = "ru"              # force Russian
SAMPLE_RATE = 16000
CHANNELS = 1
KEY_TO_RECORD = keyboard.KeyCode.from_char('a')

OUT_DIR = Path("./recordings")
OUT_DIR.mkdir(exist_ok=True)

# If True, keeps wav and mp3 files. If False, deletes wav after conversion.
KEEP_WAV = True


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

        print(f"[info] Loading Whisper model: {MODEL_NAME} ...")
        self.model = whisper.load_model(MODEL_NAME)

        if shutil.which("ffmpeg") is None:
            print("[warn] FFmpeg not found on PATH. MP3 conversion will fail.")
            print("       (Whisper can still work with WAV if you tweak the code.)")

        print("\nControls:")
        print("  - Hold 'a' to record")
        print("  - Release 'a' to transcribe")
        print("  - Press ESC to quit\n")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            # Print non-fatal stream warnings
            print(f"[audio] {status}", file=sys.stderr)

        if self.state.recording:
            # Copy to avoid referencing internal buffer
            self.audio_q.put(indata.copy())

    def start_stream(self):
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            device=24,  # change as needed
            dtype="float32",
            callback=self._audio_callback,
            blocksize=0,  # let sounddevice decide
        )
        self.stream.start()
        print("[info] Mic stream started.")

    def stop_stream(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
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
        # fp16 False for CPU; if you have CUDA torch, fp16 may be fine.
        result = self.model.transcribe(
            str(audio_path),
            language=LANGUAGE,
            task="transcribe",
            fp16=False,
            verbose=False,
        )
        return (result.get("text") or "").strip()

    def on_press(self, key):
        if key == keyboard.Key.esc:
            print("\n[info] Exiting...")
            return False

        if key == KEY_TO_RECORD and not self.state.recording:
            # Start recording
            self.state.recording = True
            self.state.started_at = time.time()
            self.state.frames = []
            print("[rec] Recording... (hold 'a')")

    def on_release(self, key):
        if key == KEY_TO_RECORD and self.state.recording:
            # Stop recording
            self.state.recording = False

            # Collect any remaining queued frames
            self._drain_queue_into_frames()

            if not self.state.frames:
                print("[rec] No audio captured.")
                return

            audio = np.concatenate(self.state.frames, axis=0).reshape(-1)

            # Basic guard against super-short taps
            duration = len(audio) / SAMPLE_RATE
            if duration < 0.15:
                print(f"[rec] Too short ({duration:.2f}s). Try again.")
                return

            # Save -> MP3 -> Whisper
            try:
                wav_path = self._save_wav(audio)
                mp3_path = self._wav_to_mp3(wav_path)

                if not KEEP_WAV:
                    try:
                        wav_path.unlink(missing_ok=True)
                    except Exception:
                        pass

                print(f"[asr] Transcribing ({duration:.2f}s) ...")
                text = self._transcribe_with_whisper(mp3_path)

                print("\n--- TRANSCRIPT ---")
                print(text if text else "(no text detected)")
                print("------------------\n")

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
