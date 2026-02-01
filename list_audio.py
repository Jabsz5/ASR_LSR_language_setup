import sounddevice as sd

print("=== Host APIs ===")
for i, api in enumerate(sd.query_hostapis()):
    print(f"{i}: {api['name']} (devices={api['devices'][:5]}{'...' if len(api['devices'])>5 else ''})")

print("\n=== Devices ===")
devs = sd.query_devices()
for i, d in enumerate(devs):
    api_name = sd.query_hostapis(d["hostapi"])["name"]
    direction = []
    if d["max_input_channels"] > 0:
        direction.append("IN")
    if d["max_output_channels"] > 0:
        direction.append("OUT")
    direction = "/".join(direction) if direction else "NONE"

    mark = "  <== YOUR 24" if i == 24 else ""
    print(
        f"{i:2d}: [{api_name:10}] {direction:6} "
        f"in={d['max_input_channels']} out={d['max_output_channels']} "
        f"default_sr={d['default_samplerate']:.0f}  {d['name']}{mark}"
    )
