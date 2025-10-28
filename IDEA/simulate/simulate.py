import os
import time
import tempfile
import requests

import gradio as gr
import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from fastapi import FastAPI
from fastrtc import (
    AdditionalOutputs,
    ReplyOnPause,
    Stream,
    get_twilio_turn_credentials,
    get_tts_model,
    KokoroTTSOptions
)
from gradio.utils import get_space
from numpy.typing import NDArray

# -----------------------------
# Load env
# -----------------------------
load_dotenv('.venv/.env')
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# -----------------------------
# ASR: NeMo Parakeet
# -----------------------------
# Model: nvidia/parakeet-tdt-0.6b-v2
# Note: This may require a GPU for good real-time performance.
import nemo.collections.asr as nemo_asr


class ParakeetSTT:
    def __init__(self):
        self.model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-0.6b-v2")
        # Optionally move to CUDA if available:
        # try:
        #     import torch
        #     if torch.cuda.is_available():
        #         self.model = self.model.to("cuda")
        # except Exception:
        #     pass

    def stt(self, audio: tuple[int, NDArray[np.int16 | np.float32]]) -> str:
        """audio = (sample_rate, np.ndarray)"""
        sr, arr = audio
        # Expecting mono. If shape is (1, N), squeeze to (N,)
        if arr.ndim > 1:
            arr = np.squeeze(arr, axis=0)

        # Ensure int16 PCM for WAV
        if arr.dtype != np.int16:
            arr = np.clip(arr, -1.0, 1.0)
            arr = (arr * 32767.0).astype(np.int16)

        # Write temp WAV and transcribe
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        try:
            sf.write(tmp_path, arr, sr, subtype="PCM_16")
            result = self.model.transcribe([tmp_path])[0]
            # Some NeMo versions return dict/list; handle both
            text = getattr(result, "text", None)
            if text is None and isinstance(result, dict):
                text = result.get("text", "")
            if text is None and isinstance(result, str):
                text = result
            return text or ""
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


stt_model = ParakeetSTT()

# -----------------------------
# LLM: Grok-4-fast via OpenRouter
# -----------------------------
class OpenRouterChat:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def chat(self, messages: list[dict], system_prompt: str | None = None) -> str:
        payload = {
            "model": "x-ai/grok-4-fast",
            "reasoning": {"enabled": False},
            "messages": [],
        }
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional but recommended:
            # "HTTP-Referer": "http://localhost:7860",
            # "X-Title": "FastRTC Voice Assistant",
        }
        resp = requests.post(self.url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


llm_client = OpenRouterChat(OPENROUTER_API_KEY)


# -----------------------------
# TTS: Kokoro (built-in)
# -----------------------------
tts_model = get_tts_model(model="kokoro")
tts_options = KokoroTTSOptions(
    voice=os.getenv("KOKORO_VOICE", "af_sarah"),
    speed=float(os.getenv("KOKORO_SPEED", "1.0")),
    lang=os.getenv("KOKORO_LANG", "en-us"),
)


# -----------------------------
# FastRTC handler
# -----------------------------
DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise voice assistant."

def response(audio: tuple[int, NDArray[np.int16 | np.float32]], session_id: str | None,chatbot: list[dict] | None = None):
    chatbot = chatbot or []
    messages = [{"role": d["role"], "content": d["content"]} for d in chatbot]

    # ASR
    t0 = time.time()
    text = stt_model.stt(audio)
    print("transcription time (s):", round(time.time() - t0, 3))
    print("user:", text)

    if not text.strip():
        return

    chatbot.append({"role": "user", "content": text})
    yield AdditionalOutputs(chatbot)
    messages.append({"role": "user", "content": text})

    # LLM
    t1 = time.time()
    response_text = llm_client.chat(messages, system_prompt=DEFAULT_SYSTEM_PROMPT)
    print("llm time (s):", round(time.time() - t1, 3))
    print("assistant:", response_text)

    chatbot.append({"role": "assistant", "content": response_text})

    # TTS: synchronous streaming
    for audio_out in tts_model.stream_tts_sync(response_text, options=tts_options):
        # audio_out is (sample_rate, np.ndarray) and can be yielded directly
        yield audio_out

    yield AdditionalOutputs(chatbot)



# -----------------------------
# Gradio + FastRTC app
# -----------------------------
chatbot = gr.Chatbot(type="messages")

stream = Stream(
    modality="audio",
    mode="send-receive",
    handler=ReplyOnPause(response, input_sample_rate=16000),
    additional_outputs_handler=lambda a, b: b,
    additional_inputs=[chatbot],
    additional_outputs=[chatbot],
    rtc_configuration=get_twilio_turn_credentials() if get_space() else None,
    concurrency_limit=5 if get_space() else None,
    time_limit=90 if get_space() else None,
    ui_args={"title": "LLM Voice Chat (Parakeet + Grok-4-fast + Kokoro + WebRTC)"},
)

app = FastAPI()
app = gr.mount_gradio_app(app, stream.ui, path="/")


if __name__ == "__main__":
    os.environ["GRADIO_SSR_MODE"] = "false"
    mode = os.getenv("MODE", "UI")
    if mode == "UI":
        stream.ui.launch(server_port=7860)
    elif mode == "PHONE":
        stream.fastphone(host="0.0.0.0", port=7860)
    else:
        stream.ui.launch(server_port=7860)