import sounddevice as sd
import soundfile as sf
import numpy as np

SAMPLE_RATE = 16000
DURATION = 3  # seconds
OUTPUT_FILE = "mic_test.wav"

print("=== AUDIO DEVICE LIST ===")
devices = sd.query_devices()
for i, d in enumerate(devices):
    print(f"[{i}] {d['name']} | inputs={d['max_input_channels']}")

default_input, default_output = sd.default.device
print("\nDefault input device index:", default_input)
print("Default output device index:", default_output)

print("\nRecording 3 seconds from default microphone...")
audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
    device=24 # this is the audio index we need for current mic. Change as needed. 
)

sd.wait()
print("Recording finished.")

sf.write(OUTPUT_FILE, audio, SAMPLE_RATE)
print(f"Saved to {OUTPUT_FILE}")

print("\nPlaying it back...")
sd.play(audio, SAMPLE_RATE)
sd.wait()

print("\nDone. If you heard your voice, your mic is working.")
