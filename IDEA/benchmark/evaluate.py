import warnings
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent")

import time
from datetime import datetime
from docx import Document
import io
import base64
from openai import OpenAI
import tempfile
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import re
import requests
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lookups import *

def create_prompt(prompt: str, rubric: dict) -> str:
    prompt = prompt.replace("<title></title>", f"<title>{rubric['title']}</title>")
    prompt = prompt.replace("<desc></desc>", f"<desc>{rubric['desc']}</desc>")

    def format_rubric(rubric: dict) -> str:
        lines = ["FEATURES:"]
        for key, desc in rubric['features'].items():
            lines.append(f"\t{key}. {desc}")
        
        lines.append("\nSCORING:")
        for points, criteria in rubric['points'].items():
            lines.append(f"\t{points} points: {criteria}")
        
        return "\n".join(lines)
    
    formatted_rubric = format_rubric(rubric)
    prompt = prompt.replace("<rubric></rubric>", f"<rubric>{formatted_rubric}</rubric>")

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
    # feedback = extract("feedback")

    return {
        'comment': rationale,
        'features': features,
        'score': score,
        # 'feedback': feedback
    }

# https://openrouter.ai/docs/api-reference/chat-completion
def generate(model_info: dict, base_prompt: str, rubric: dict, user_prompt: str) -> dict:
    system_prompt = create_prompt(base_prompt, rubric)

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model_info['id'],
        "reasoning":{
            "enabled": True
        },
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    raw = requests.post(url, json=payload, headers=headers)
    raw = raw.json()

    output = raw['choices'][0]['message']['content']
    eval = extract_from_output(output) # reasoning, grade, feedback
    usage = {
        'input_tokens': raw['usage']['prompt_tokens'],
        'output_tokens': raw['usage']['completion_tokens']
    }
    eval['usage'] = usage

    return eval


def evaluate(model_id: str, which: str, netid = None, patient = None) -> None:
    # DB SETTINGS
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    target = client['Benchmark']['AI_Eval.M2_test_exp']
    
    # GET SIMS TO EVAL
    sims = ""
    if which == "single":
        sims = [source.find_one({"netid": netid, "patient": patient})] # FIND THE SINGLE
    elif which in ["all", "rem"]:
        sims = list(source.find({}, {"netid": 1, "patient": 1, "post_note_inputs": 1}))
        if which == "rem":
            sims = [sim for sim in sims if not target.find_one({"model_info.id": model_id,
                                                                "sim_info.netid": sim['netid'],
                                                                "sim_info.patient": sim['patient']})]
    
    # MODEL SETTINGS
    model_info = {
        "id": model_id,
        "temperature": None,
        "thinking": True,
        "prompt_id": "Evaluate_10-5-25",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0
        }
    }
    
    # EVAL PROMPT
    with open(f"./Prompts/{model_info['prompt_id']}.txt", 'r') as prompt_file:
        base_prompt = prompt_file.read()

    n = 0
    for sim in sims:
        start_time = datetime.now()

        sim_info = {
            "_id": sim['_id'],
            "netid": sim['netid'],
            "patient": sim['patient'], 
        }

        n += 1
        print(f"({n}/{len(sims)}) {sim['netid']} | {sim['patient']}")

        evaluation = {}
        post_note = sim['post_note_inputs']
        for section in RUBRIC:
            student_response = post_note[section]
            if not student_response:
                evaluation[section] = None
                continue
            
            evaluation[section] = {}
            for part, rubric in RUBRIC[section].items():
                user_prompt = f"<{section}>{student_response}</{section}>"
                if "extra_context" in rubric:
                    user_prompt = f"<{section}>{student_response}</{section}>"
                    extra = rubric['extra_context']
                    user_prompt += f"\n<{extra}>{post_note[extra]}</{extra}>"

                part_eval = generate(model_info, base_prompt, rubric, user_prompt)
                part_usage = part_eval.pop('usage')
                model_info['usage']['input_tokens'] += part_usage['input_tokens']
                model_info['usage']['output_tokens'] += part_usage['output_tokens']
                evaluation[section][part] = part_eval

        end_time = datetime.now()
        delta = abs(start_time - end_time)
        time_spent = delta.total_seconds() / 60

        final_result = {
            "username": model_id,
            "model_info": model_info,
            "sim_info": sim_info,
            "rubric_id": RUBRIC_ID,
            "evaluation": evaluation,
            "time_spent": time_spent,
        }

        target.insert_one(final_result)


if __name__ == "__main__":
    evaluate(
        model_id = "anthropic/claude-sonnet-4.5",
        which = "rem",
        # netid = "mi360",
        # patient = "Jeffrey Smith"
    )