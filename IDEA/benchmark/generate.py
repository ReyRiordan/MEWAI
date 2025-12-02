import time
from datetime import datetime
from docx import Document
import io
import os
import base64
import json
import tempfile
from annotated_text import annotated_text
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import re

from openai import OpenAI
from anthropic import Anthropic
from google import genai


def create_prompt(prompt: str, rubric: dict) -> str:
    prompt = prompt.replace("<title></title>", f"<title>{rubric['title']}</title>")
    prompt = prompt.replace("<desc></desc>", f"<desc>{rubric['desc']}</desc>")
    exclude = ['title', 'desc', 'html', 'extra_context']
    to_insert = {k: v for k, v in rubric.items() if k not in exclude}
    prompt = prompt.replace("<rubric></rubric>", f"<rubric>{to_insert}</rubric>")

    return prompt


def extract_from_output(output: str) -> dict:

    def extract(tag: str):
        match = re.search(rf'<{tag}>([\s\S]*?)</{tag}>', output)
        if match:
            return match.group(1).strip()
        else:
            print(f"ERROR: no match for <{tag}> in output")
            return None

    rationale = extract("rationale")
    raw_grades = extract("grades")
    if raw_grades:
        try:
            grade_dict = json.loads(raw_grades)
            features = grade_dict['features']
            score = grade_dict['score']
        except json.JSONDecodeError as e:
            print(f"ERROR: Could not parse grade JSON '{raw_grades}': {e}")
            grade_dict = features = score = None
    else:
        grade_dict = features = score = None
    feedback = extract("feedback")

    return {
        'comment': rationale,
        'features': features,
        'score': score,
        'feedback': feedback
    }


# https://docs.anthropic.com/en/api/messages
def generate_anthropic(model_info: dict, system_prompt: str, user_prompt: str) -> dict:
    client = Anthropic()

    # Generate output
    # prefill = "<reasoning>"
    raw_output = client.messages.create(
            model = model_info['name'],
            temperature = 1, # REQUIRED FOR THINKING
            system = system_prompt,
            thinking = {
                "type": "enabled",
                "budget_tokens": 2048
            },
            max_tokens = 4096,
            messages = [
                {"role": "user", "content": user_prompt},
                # {"role": "assistant", "content": prefill}
            ]
        )
    output = raw_output.content[1].text
    # print(output)

    eval = extract_from_output(output) # reasoning, grade, feedback
    usage = {
        'input_tokens': raw_output.usage.input_tokens,
        'output_tokens': raw_output.usage.output_tokens
    }
    eval['usage'] = usage

    return eval


# https://platform.openai.com/docs/api-reference/responses/create
def generate_openai(model_info: dict, system_prompt: str, user_prompt: str) -> dict:
    client = OpenAI()

    # Generate output
    raw_output = client.responses.create(
            model = model_info['name'],
            # temperature = model_info['temperature'], # NOT SUPPORTED WITH GPT5?
            instructions = system_prompt,
            reasoning = {
                'effort': 'medium',
            },
            input = user_prompt
        )
    output = raw_output.output[1].content[0].text
    # print(output)
    
    eval = extract_from_output(output) # reasoning, grade, feedback
    usage = {
        'input_tokens': raw_output.usage.input_tokens,
        'output_tokens': raw_output.usage.output_tokens
    }
    eval['usage'] = usage

    return eval


# https://ai.google.dev/api/generate-content
def generate_google(model_info: dict, system_prompt: str, user_prompt: str) -> dict:
    client = genai.Client()

    # Generate output
    raw_output = client.models.generate_content(
            model = model_info['name'],
            config=genai.types.GenerateContentConfig(
                temperature = model_info['temperature'],
                system_instruction = system_prompt,
                thinking_config = genai.types.ThinkingConfig(thinking_budget=-1) # dynamic thinking
            ),
            contents = user_prompt
        )
    output = raw_output.text
    # print(output)

    eval = extract_from_output(output) # reasoning, grade, feedback
    usage = {
        'input_tokens': raw_output.usage_metadata.prompt_token_count,
        'output_tokens': raw_output.usage_metadata.candidates_token_count
    }
    eval['usage'] = usage

    return eval


def generate_eval(model_info: dict, base_prompt: str, rubric: dict, user_prompt: str) -> dict:
    eval = None
    system_prompt = create_prompt(base_prompt, rubric)
    provider = model_info['provider']

    if provider == "anthropic":
        eval = generate_anthropic(model_info, system_prompt, user_prompt)
    elif provider == "openai":
        eval = generate_openai(model_info, system_prompt, user_prompt)
    elif provider == "google":
        eval = generate_google(model_info, system_prompt, user_prompt)

    return eval