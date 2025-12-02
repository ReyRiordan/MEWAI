import time
from datetime import datetime
import io
import os
import base64
import json
import tempfile
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from openai import OpenAI
from anthropic import Anthropic
from google import genai
import matplotlib.pyplot as plt
import pandas as pd

from dotenv import load_dotenv
load_dotenv('.venv/.env')
DB_URI = os.getenv("DB_URI")


# Compute time elapsed in minutes from ISOs
def elapsed_minutes(iso1: str, iso2: str) -> int:
    t1 = datetime.fromisoformat(iso1)
    t2 = datetime.fromisoformat(iso2)
    delta = abs(t2 - t1)
    return delta.total_seconds() / 60

def compute_time_spent(source):
    docs = list(source.find())

    for doc in docs:
        total = 0
        start = None
        times = list(doc['times'].items())
        for index, (time, type) in enumerate(times):
            if type == "start":
                if index != 0 and times[index-1][1] == "mark": # if they didn't "end" the previous sesh
                    total += elapsed_minutes(start, times[index-1][0])
                start = time
            elif type == "end":
                total += elapsed_minutes(start, time)
            elif index == len(times)-1 and type == "mark":
                total += elapsed_minutes(start, time)

        doc['time_spent'] = total
        source.replace_one({"_id": doc['_id']}, doc)


def check_eval_order(source):
    evals = list(source.find())

    eval_lists = {
        "Fac1": [],
        "Fac2": [],
        "Fac3": []
    }
    for eval in evals:
        to_append = {
            'sim_netid': eval['sim_info']['netid'],
        }
        start_time = None
        for time, mark in eval['times'].items():
            if mark == "start":
                start_time = time
            elif mark == "mark" or mark == "save":
                break
        to_append['start_time'] = start_time

        eval_lists[eval['username']].append(to_append)
    
    for fac, items in eval_lists.items():
        items.sort(key=lambda x: x['start_time'])
        ids = [item['sim_netid'] for item in items]
        print(fac, ids)


def fatigue():
    faculty = ["Fac1", "Fac2", "Fac3"]
    AI = "anthropic/claude-sonnet-4.5"
    client = MongoClient(DB_URI)
    source_group = client['Benchmark']['Group_Eval.M2_test']
    source_AI = client['Benchmark']['AI_Eval.M2_test_flag']
    source_human = client['Benchmark']['Human_Eval.M2_test_copy']
    evals = list(source_human.find())
    ai_evals = list(source_AI.find({'username': AI}, 
                             {'_id': 0, 'username': 1, 'sim_info': 1, 'evaluation': 1, 'time_spent': 1}))

    eval_lists = {fac: [] for fac in faculty}
    for eval in evals:
        to_append = {
            'sim_id': eval['sim_info']['_id'],
            'duration': eval['time_spent']
        }

        # start time
        start_time = None
        for time, mark in eval['times'].items():
            if mark == "start":
                start_time = time
            elif mark == "mark" or mark == "save":
                break
        to_append['start_time'] = start_time

        # feature mistakes
        mistakes = 0
        group_eval = source_group.find_one({'sim_info._id': eval['sim_info']['_id']})
        for section in group_eval['evaluation']:
            for part in group_eval['evaluation'][section]:
                correct_features = group_eval['evaluation'][section][part]['features']

                for feature, grade in eval['evaluation'][section][part]['features'].items():
                    if correct_features[feature] == True and grade == False:
                        mistakes += 1
                    elif correct_features[feature] == False and grade == True:
                        mistakes += 1
        to_append['mistakes'] = mistakes

        eval_lists[eval['username']].append(to_append)
    
    # prepare data
    durations = {fac: [] for fac in faculty}
    mistakes = {fac: [] for fac in faculty}
    for fac, items in eval_lists.items():
        items.sort(key=lambda x: x['start_time'])
        durations[fac] = [item['duration'] for item in items]
        mistakes[fac] = [item['mistakes'] for item in items]
    durations[AI] = []
    for eval in ai_evals:
        durations[AI].append(eval['time_spent'])

    # plot
    plt.figure()
    for fac in faculty + [AI]:
        plt.plot(durations[fac], label=fac)
    plt.xlabel("# evaluated")
    plt.ylabel("duration (min)")
    plt.title(f"Fatigue (duration)")
    plt.legend()
    plt.show()

    accuracy = {}
    for fac, mlist in mistakes.items():
        accuracy[fac] = [(24-m)/24 for m in mlist]
    plt.figure()
    for fac in faculty:
        plt.plot(accuracy[fac], label=fac)
    plt.xlabel("# evaluated")
    plt.ylabel("accuracy (features)")
    plt.title(f"Fatigue (accuracy)")
    plt.legend()
    plt.show()


def flagged_breakdown():
    model = "google/gemini-3-pro-preview"
    client = MongoClient(DB_URI)
    source = client['Benchmark']['AI_Eval.M2_test_flag_2']
    evals = list(source.find({'username': model}, 
                             {'_id': 0, 'username': 1,'sim_info': 1, 'evaluation': 1}))
    
    breakdown = {}
    total = 0
    for eval in evals:
        for section in eval['evaluation']:
            for feature, grading in eval['evaluation'][section]['features'].items():
                if grading['flag']:
                    total += 1
                    label = f"{section} {feature}"
                    if label in breakdown:
                        breakdown[label] += 1
                    else:
                        breakdown[label] = 1
    
    print(f"----- FLAGGED ITEMS BREAKDOWN: {model} (total={total}) -----")
    for label, count in breakdown.items():
        print(f"{label}: {count}")
    


if __name__ == "__main__":
    # client = MongoClient(DB_URI)
    # source = client['Benchmark']['Human_Eval.M2_test_copy']
    flagged_breakdown()