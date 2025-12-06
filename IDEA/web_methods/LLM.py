from docx import Document
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName,
    FileType, Disposition, ContentId)
import os
import datetime as date
import base64
import io
import streamlit as st
from audiorecorder import audiorecorder
from openai import OpenAI
from anthropic import Anthropic
from google import genai
import requests

import tempfile
from annotated_text import annotated_text
import json
import time
from email.mime.text import MIMEText
import smtplib

from lookups import *
from web_classes.message import Message
from web_classes.patient import Patient


def generate_feedback(title: str, desc: str, rubric: str, user_input: str, tokens: dict, model=FEEDBACK_MODEL, temperature=FEEDBACK_TEMP):
    base_split = FEEDBACK_PROMPT.split("[INSERT]")
    prefill = "Correct"
    if not user_input:
        user_input = "NO INPUT"
    system = base_split[0] + title + base_split[1] + desc + base_split[2] + rubric + base_split[3] + user_input

    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = FEEDBACK_CLIENT.messages.create(
                model=model,
                temperature=temperature,
                max_tokens=4096,
                system=system,
                messages=[
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": prefill}
                ]
            )
            # st.session_state["tokens"]["feedback"]["input"] += response.usage.input_tokens
            # st.session_state["tokens"]["feedback"]["output"] += response.usage.output_tokens
            tokens['input'] += response.usage.input_tokens
            tokens['output'] += response.usage.output_tokens
            return prefill + response.content[0].text
        except Exception as e:
            print(e)
            print("\n\n")
            if attempt == MAX_ATTEMPTS:
                error_details = f"Error: {e}"
                msg = MIMEText(error_details)
                msg["Subject"] = st.session_state["username"] + " FEEDBACK ERROR"
                msg["From"] = "rutgers.aime@gmail.com"
                msg["To"] = "rhr58@scarletmail.rutgers.edu"
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.starttls()
                    server.login("rutgers.aime@gmail.com", "klwlvaxxkpejpsuu")
                    server.send_message(msg)
                st.session_state["error_details"] = error_details
                st.session_state["stage"] = ERROR
                st.rerun()
            else:
                st.write(f"Attempt {attempt} failed. Retrying in {backoff} seconds")
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff


def generate_response(model: str, temperature: float, system_prompt: str, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": "anthropic/claude-haiku-4.5",
        "reasoning": {"enabled": False},
        "messages": [],
    }
    if system_prompt:
        payload["messages"].append({"role": "system", "content": system_prompt})
    payload["messages"].extend(messages)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    raw = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                         json=payload, headers=headers, timeout=120)
    raw.raise_for_status()
    data = raw.json()
    
    st.session_state["tokens"]["convo"]["input"] += data['usage']['prompt_tokens']
    st.session_state["tokens"]["convo"]["output"] += data['usage']['completion_tokens']
    return data["choices"][0]["message"]["content"]


def transcribe_voice(voice_input):
    temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    voice_input.export(temp_audio_file.name, format="wav")
    with open(temp_audio_file.name, "rb") as file:
        transcription = STT.audio.transcriptions.create(model = STT_MODEL, 
                                                        file = file, 
                                                        response_format = "text")
    return transcription


def generate_voice(patient: Patient, text_input: str) -> io.BytesIO:
    bio = io.BytesIO()
    speech = TTS.audio.speech.create(model = TTS_MODEL, 
                                     voice = patient.speech["Voice"], 
                                     response_format = "wav", 
                                     input = text_input)
    bio.write(speech.content)
    return bio


def play_voice(bio: io.BytesIO) -> None:
    # Convert the audio data in the BytesIO buffer to base64
    audio_base64 = base64.b64encode(bio.getvalue()).decode('utf-8')
    # Generate the HTML audio tag with autoplay
    audio_tag = f'<audio autoplay="true" src="data:audio/wav;base64,{audio_base64}">'
    # Display the audio tag using Streamlit markdown
    st.markdown(audio_tag, unsafe_allow_html=True)


def get_chat_output(user_input: str):
    st.session_state["interview"].add_message(Message(type="input", role="User", content=user_input))
    st.session_state["messages"].append({"role": "user", "content": user_input})
    st.session_state["convo_memory"].append({"role": "user", "content": user_input})

    response = generate_response(model = CONVO_MODEL, 
                                 temperature = CONVO_TEMP, 
                                 system_prompt = st.session_state["convo_prompt"] + st.session_state["convo_summary"], 
                                 messages = st.session_state["convo_memory"])
    
    speech = generate_voice(st.session_state["interview"].patient, response)

    st.session_state["interview"].add_message(Message(type="output", role="AI", content=response))
    st.session_state["messages"].append({"role": "assistant", "content": response})
    st.session_state["convo_memory"].append({"role": "assistant", "content": response})

    if len(st.session_state["convo_memory"]) >= MAX_MEMORY:
        conversation = json.dumps(st.session_state["messages"][:-2]) # exclude last 2 messages for smoother convo
        summary = generate_response(model = SUM_MODEL, 
                                temperature = SUM_TEMP, 
                                system = SUM_PROMPT + conversation, 
                                messages = [{"role": "user", "content": conversation}])
        # print("Summary: " + summary + "\n") # bug fixing

        st.session_state["convo_summary"] = "\nSummary of conversation so far: \n" + summary # overwrite summary
        st.session_state["convo_memory"] = st.session_state["convo_memory"][-2:]
        
        # AUTO SAVE
        st.session_state["interview"].store_convo_data()
        st.session_state["interview"].record_time("save_interview")
        COLLECTION.replace_one({"username" : st.session_state["username"], 
                            "start_time" : st.session_state["start_time"]}, 
                            st.session_state["interview"].model_dump())

    return response, speech