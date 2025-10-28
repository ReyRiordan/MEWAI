from fastrtc import get_tts_model, KokoroTTSOptions

tts = get_tts_model(model="kokoro")
options = KokoroTTSOptions(voice="af_sarah", speed=1.0, lang="en-us")

chunks = 0
for sr, audio in tts.stream_tts_sync("Testing the Kokoro TTS via FastRTC.", options=options):
    print("chunk:", chunks, "sr:", sr, "shape:", audio.shape, "dtype:", audio.dtype)
    chunks += 1
    if chunks > 3:
        break

print("OK: streamed first few chunks")