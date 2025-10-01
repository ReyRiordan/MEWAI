import time
from datetime import datetime
from docx import Document
import io
import base64
from openai import OpenAI
import tempfile
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lookups import *
from generate import *


def evaluate(model_id: str, which: str, netid = None, patient = None) -> None:
    # DB SETTINGS
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    target = client['Benchmark']['AI_Eval.M2_test']
    
    # GET SIMS TO EVAL
    sims = ""
    if which == "single":
        sims = [source.find_one({"netid": netid, "patient": patient})] # FIND THE SINGLE
    elif which in ["all", "rem"]:
        sims = list(source.find({}, {"netid": 1, "patient": 1}))
        if which == "rem":
            sims = [header for header in sims if not target.find_one({"model_info.id": model_id,
                                                                      "sim_info.netid": header['netid'],
                                                                      "sim_info.patient": header['patient']})]
    
    # MODEL SETTINGS
    model_info = {
        "id": model_id,
        "temperature": 0.0,
        "thinking": True,
        "prompt_id": "Feedback_8-22",
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
                if "extra_context" in rubric:
                    extra = rubric['extra_context']
                    user_prompt += f"\n<{extra}>{post_note[extra]}</{extra}>"
                else:
                    user_prompt = f"<{section}>{student_response}</{section}>"

                part_eval = generate_eval(model_info, base_prompt, rubric, user_prompt)
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


def evaluate_all(provider: str, model_name: str, username: str):
    # DB SETTINGS
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    target = client['Benchmark']['AI_Eval.M2_test']
    sim_headers = list(source.find({}, {"netid": 1, "patient": 1}))
    # MODEL SETTINGS
    model_info = {
        "provider": provider,
        "name": model_name,
        "temperature": 0.0,
        "thinking": True,
        "prompt_id": "Feedback_8-22",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0
        }
    }
    # EVAL PROMPT
    with open(f"./Prompts/{model_info['prompt_id']}.txt", 'r') as prompt_file:
        base_prompt = prompt_file.read()

    n = 0
    for header in sim_headers:
        sim = source.find_one({"_id": header['_id']})
        start_time = datetime.now()

        sim_info = {
            "_id": sim['_id'],
            "netid": sim['netid'],
            "patient": sim['patient'], 
        }

        n += 1
        print(f"({n}/{len(sim_headers)}) {sim['netid']} | {sim['patient']}")

        evaluation = {}
        post_note = sim['post_note_inputs']
        for section in RUBRIC:
            student_response = post_note[section]
            if not student_response:
                evaluation[section] = None
                continue
            
            evaluation[section] = {}
            for part, rubric in RUBRIC[section].items():
                if "extra_context" in rubric:
                    extra = rubric['extra_context']
                    user_prompt += f"\n<{extra}>{post_note[extra]}</{extra}>"
                else:
                    user_prompt = f"<{section}>{student_response}</{section}>"

                part_eval = generate_eval(model_info, base_prompt, rubric, user_prompt)
                part_usage = part_eval.pop('usage')
                model_info['usage']['input_tokens'] += part_usage['input_tokens']
                model_info['usage']['output_tokens'] += part_usage['output_tokens']
                evaluation[section][part] = part_eval

        end_time = datetime.now()
        delta = abs(start_time - end_time)
        time_spent = delta.total_seconds() / 60

        final_result = {
            "username": username,
            "model_info": model_info,
            "sim_info": sim_info,
            "rubric_id": RUBRIC_ID,
            "evaluation": evaluation,
            "time_spent": time_spent,
        }

        target.insert_one(final_result)


def evaluate_rem(provider: str, model_name: str, username: str):
    # DB SETTINGS
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    target = client['Benchmark']['AI_Eval.M2_test']
    sim_headers = list(source.find({}, {"netid": 1, "patient": 1}))
    # FILTER TO ONLY REMAINDERS
    sim_headers = [header for header in sim_headers 
                   if not target.find_one({"model_info.provider": provider,
                                           "sim_info.netid": header['netid'],
                                           "sim_info.patient": header['patient']})]
    # MODEL SETTINGS
    model_info = {
        "provider": provider,
        "name": model_name,
        "temperature": 0.0,
        "thinking": True,
        "prompt_id": "Feedback_8-22",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0
        }
    }
    # EVAL PROMPT
    with open(f"./Prompts/{model_info['prompt_id']}.txt", 'r') as prompt_file:
        base_prompt = prompt_file.read()

    n = 0
    for header in sim_headers:
        sim = source.find_one({"_id": header['_id']})
        start_time = datetime.now()

        sim_info = {
            "_id": sim['_id'],
            "netid": sim['netid'],
            "patient": sim['patient'], 
        }

        n += 1
        print(f"({n}/{len(sim_headers)}) {sim['netid']} | {sim['patient']}")

        evaluation = {}
        post_note = sim['post_note_inputs']
        for section in RUBRIC:
            student_response = post_note[section]
            if not student_response:
                evaluation[section] = None
                continue
            
            evaluation[section] = {}
            for part, rubric in RUBRIC[section].items():
                if "extra_context" in rubric:
                    extra = rubric['extra_context']
                    user_prompt += f"\n<{extra}>{post_note[extra]}</{extra}>"
                else:
                    user_prompt = f"<{section}>{student_response}</{section}>"
                
                part_eval = generate_eval(model_info, base_prompt, rubric, user_prompt)
                part_usage = part_eval.pop('usage')
                model_info['usage']['input_tokens'] += part_usage['input_tokens']
                model_info['usage']['output_tokens'] += part_usage['output_tokens']
                evaluation[section][part] = part_eval

        end_time = datetime.now()
        delta = abs(start_time - end_time)
        time_spent = delta.total_seconds() / 60

        final_result = {
            "username": username,
            "model_info": model_info,
            "sim_info": sim_info,
            "rubric_id": RUBRIC_ID,
            "evaluation": evaluation,
            "time_spent": time_spent,
        }

        target.insert_one(final_result)


def evaluate_single(provider: str, model_name: str, username: str, netid: str, patient: str):
    # DB SETTINGS
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    target = client['Benchmark']['AI_Eval.M2_test']
    # MODEL SETTINGS
    model_info = {
        "provider": provider,
        "name": model_name,
        "temperature": 0.0,
        "thinking": True,
        "prompt_id": "Feedback_8-22",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0
        }
    }
    # EVAL PROMPT
    with open(f"./Prompts/{model_info['prompt_id']}.txt", 'r') as prompt_file:
        base_prompt = prompt_file.read()

    start_time = datetime.now().isoformat()

    sim = source.find_one({"netid": netid, "patient": patient}) # FIND THE SINGLE
    sim_info = {
        "_id": sim['_id'],
        "netid": sim['netid'],
        "patient": sim['patient'], 
    }

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
                extra = rubric['extra_context']
                user_prompt += f"\n<{extra}>{post_note[extra]}</{extra}>"
            
            part_eval = generate_eval(model_info, base_prompt, rubric, user_prompt)
            part_usage = part_eval.pop('usage')
            model_info['usage']['input_tokens'] += part_usage['input_tokens']
            model_info['usage']['output_tokens'] += part_usage['output_tokens']
            evaluation[section][part] = part_eval

    end_time = datetime.now().isoformat()
    times = {
        start_time: "start",
        end_time: "end"
    }

    final_result = {
        "username": username,
        "model_info": model_info,
        "sim_info": sim_info,
        "rubric_id": RUBRIC_ID,
        "evaluation": evaluation,
        "times": times,
    }

    target.insert_one(final_result)


def evaluate_old(type: str, provider: str, netid = None, patient = None):
    models = {
        "anthropic": {
            "name": "claude-sonnet-4-20250514",
            "username": "Claude 4S"
        },
        "openai": {
            "name": "gpt-5",
            "username": "GPT 5"
        },
        "google": {
            "name": "gemini-2.5-pro",
            "username": "Gemini 2.5P"
        }
    }

    if type == "all":
        evaluate_all(
            provider = provider,
            model_name = models[provider]['name'],
            username = models[provider]['username'],
        )

    elif type == "rem":
        evaluate_rem(
            provider = provider,
            model_name = models[provider]['name'],
            username = models[provider]['username'],
        )

    elif type == "single":
        evaluate_single(
            provider = provider,
            model_name = models[provider]['name'],
            username = models[provider]['username'],
            netid = netid,
            patient = patient
        )

    else:
        print("ERROR")


if __name__ == "__main__":
    evaluate(
        model_id = "x-ai/grok-4-fast:free",
        which = "all"
        # netid = "mi360",
        # patient = "Jeffrey Smith"
    )