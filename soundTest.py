"""
Hold-to-record audio test (Windows)
- Hold 'a' to record from input device index 24
- Release 'a' to stop and save WAV
- ESC to quit

Install:
  pip install sounddevice soundfile numpy pynput
"""

import time
import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard
from pathlib import Path

SAMPLE_RATE = 16000
CHANNELS = 1
INPUT_DEVICE_INDEX = 24
KEY_TO_RECORD = keyboard.KeyCode.from_char('a')

OUT_DIR = Path("./test_recordings")
OUT_DIR.mkdir(exist_ok=True)

audio_q = queue.Queue()
frames = []
recording = False
stream = None

def audio_callback(indata, frames_count, time_info, status):
    if status:
        print(f"[audio] {status}")
    if recording:
        audio_q.put(indata.copy())

def start_stream():
    global stream
    # More conservative settings than float32 + blocksize=0
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        device=INPUT_DEVICE_INDEX,
        dtype="int16",          # often safer on Windows drivers
        blocksize=1024,         # avoid 0 (driver-dependent)
        latency="high",         # stability > responsiveness for this test
        callback=audio_callback,
    )
    stream.start()

def stop_stream():
    global stream
    if stream is not None:
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
        stream = None

def on_press(key):
    global recording, frames

    if key == keyboard.Key.esc:
        print("Exiting...")
        return False

    if key == KEY_TO_RECORD and not recording:
        recording = True
        frames = []

        # clear queue
        while not audio_q.empty():
            try:
                audio_q.get_nowait()
            except queue.Empty:
                break

        try:
            start_stream()
            print("[rec] Recording...")
        except Exception as e:
            recording = False
            stop_stream()
            print(f"[error] Could not start stream on device {INPUT_DEVICE_INDEX}: {e}")

def on_release(key):
    global recording

    if key == KEY_TO_RECORD and recording:
        recording = False
        stop_stream()

        # drain queue
        while not audio_q.empty():
            try:
                frames.append(audio_q.get_nowait())
            except queue.Empty:
                break

        if not frames:
            print("[rec] No audio captured")
            return

        audio = np.concatenate(frames, axis=0)

        # audio is int16 already; save as PCM_16
        duration = audio.shape[0] / SAMPLE_RATE
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = OUT_DIR / f"test_{ts}.wav"
        sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")

        print(f"[rec] Saved {path} ({duration:.2f}s)")

print("Hold 'a' to record | Release to stop | ESC to quit")

listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()
listener.join()

stop_stream()
