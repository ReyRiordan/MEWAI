import time
from datetime import datetime
from docx import Document
import io
import os
import streamlit as st
import streamlit.components.v1 as components
# import streamlit_authenticator as auth
import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName,
    FileType, Disposition, ContentId)
from audiorecorder import audiorecorder
from openai import OpenAI
import tempfile
from annotated_text import annotated_text
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from lookups import *
from web_classes import *
from web_methods import *
import pytz
import random
import re


def copy_post_notes():
    client = MongoClient(DB_URI)

    sources = ["M1", "M2"]
    target_db = client["Benchmark"]["Interviews"]

    for source_name in sources:
        source_collection = client[source_name]["Interviews"]
        target_collection = target_db[source_name]

        # Filter where feedback is not null
        filtered_docs = source_collection.find({
            "feedback": {"$ne": None}
        })

        # Add "group" (M1/M2), change "username" to "netid"
        modified_docs = []
        for doc in filtered_docs:
            doc["group"] = source_name
            doc["netid"] = doc["username"]
            del doc["username"]
            patient = doc["patient"]["id"]
            del doc["patient"]
            doc["patient"] = patient
            del doc["feedback"]
            doc["post_note"] = doc.pop("post_note_inputs")
            doc.pop("convo_data", None)
            doc.pop("_id", None)  # Remove _id to avoid conflict
            modified_docs.append(doc)

        if modified_docs:
            target_collection.insert_many(modified_docs)
            print(f"Copied {len(modified_docs)} documents from {source_name}")
        else:
            print(f"No documents to copy for {source_name}")

def manual_filter():
    client = MongoClient(DB_URI)
    source = client["Benchmark"]["Interviews.M1"]

    docs = list(source.find({}, {"netid": 1, "patient": 1, "post_note_inputs": 1}))

    n = 1
    for doc in docs:
        print(f"{n}/338------------------------{doc['netid']}: {doc['patient']}---------------------------------------------")
        print(doc.get("post_note_inputs", "NO POST NOTE"))
        response = input("Keep this doc? (y/n): ").strip().lower()
        if response == "n":
            source.delete_one({"_id": doc["_id"]})
        n += 1

def select_eval_set():
    client = MongoClient(DB_URI)
    source = client["Benchmark"]["Interviews"]["M2"]
    eval_test = client["Benchmark"]["Interviews"]["M2_test"]
    eval_rem = client["Benchmark"]["Interviews"]["M2_rem"]

    # retrieve all and random shuffle
    all_docs = list(source.find())
    random.shuffle(all_docs)

    # split into groups by patient
    groups = {"Jeffrey Smith": [],
              "Jenny Smith": [],
              "Samuel Thompson": [],
              "Sarah Thompson": []}
    for doc in all_docs:
        groups[doc["patient"]].append(doc)

    # select 40 (10 for each patient, all unique students)
    selected = []
    used = set()
    for patient, docs in groups.items():
        group_selected = []
        for doc in docs:
            if doc["netid"] not in used:
                group_selected.append(doc)
                used.add(doc["netid"])
            if len(group_selected) == 10:
                break
        selected.extend(group_selected)

    # get remaining
    selected_ids = {doc["_id"] for doc in selected}
    remaining = [doc for doc in all_docs if doc["_id"] not in selected_ids]
    
    # store each
    for doc in selected:
        doc.pop("_id", None)
    eval_test.insert_many(selected)
    for doc in remaining:
        doc.pop("_id", None)
    eval_rem.insert_many(remaining)

def add_sexes():
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M1']
    all_docs = list(source.find())

    with open('IDEA/assignments/M1.json', 'r') as M1_file:
        M1 = json.load(M1_file)

    for doc in all_docs:
        info = M1[doc['netid']]
        doc['sex'] = info['sex']
        doc['post_note_inputs'] = doc['post_note']
        del doc['post_note']
        source.replace_one({'_id': doc['_id']}, doc)

def benchmark():
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    target = client['Benchmark']['AI_Eval.M2_test']

    interviews = list(source.find())
    for interview in interviews:
        start_time = datetime.now().isoformat()
        patient = Patient.build(interview['patient'])
        feedback = Feedback.build(short = True,
                                  patient = patient,
                                  messages = interview['messages'],
                                  post_note_inputs = interview['post_note_inputs'])
        feedback = feedback.model_dump()
        feedback['info']['netid'] = interview['netid']
        feedback['info']['netid'] = interview['sex']
        feedback['info']['patient_id'] = interview['patient']
        feedback['info']['interview_id'] = interview['_id']
        end_time = datetime.now().isoformat()
        feedback['times'] = [start_time, end_time]

        target.insert_one(feedback)
        print(f"Completed {interview['netid']}: {interview['patient']}")

        break # test with one

# Compute time elapsed in minutes from ISOs
def elapsed_minutes(iso1: str, iso2: str) -> int:
    t1 = datetime.fromisoformat(iso1)
    t2 = datetime.fromisoformat(iso2)
    delta = abs(t2 - t1)
    return int(delta.total_seconds() // 60)

def research_data():
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M1']
    target = client['Research']['Data.M1']

    with open('./Prompts/research_data.txt', 'r') as file:
        prompt = file.read()

    interviews = list(source.find())
    n = 0
    max_id = 0
    student_list = {}
    StudentID = None
    for interview in interviews:
        n += 1
        # StudentID
        if interview['netid'] in student_list:
            StudentID = student_list[interview['netid']]
        else:
            max_id += 1
            student_list[interview['netid']] = max_id
            StudentID = max_id
        print(f"--------{n}/330---------")
        dict1 = {'interview_id': interview['_id'],
                 'netid': interview['netid'],
                 'StudentID': StudentID}
        # StudentSex
        if interview['sex'] == 'M':
            dict1['StudentSex'] = 0
        elif interview['sex'] == 'F':
            dict1['StudentSex'] = 1
        else: print(f"Interview {interview['_id']} has error sex value {interview['sex']}.")
        # Year
        dict1['Year'] = 0
        # CaseNum
        if interview['patient'] in ["Jeffrey Smith", "Jenny Smith"]:
            dict1['CaseNum'] = 0
        elif interview['patient'] in ["Samuel Thompson", "Sarah Thompson"]:
            dict1['CaseNum'] = 1
        else: print(f"Interview {interview['_id']} has error patient value {interview['patient']}.")
        # CaseSex
        if interview['patient'] in ["Jeffrey Smith", "Samuel Thompson"]:
            dict1['CaseSex'] = 0
        elif interview['patient'] in ["Jenny Smith", "Sarah Thompson"]:
            dict1['CaseSex'] = 1
        else: print(f"Interview {interview['_id']} has error patient value {interview['patient']}.")
        
        # Process LLM input
        if dict1['CaseSex'] == 0:
            correct_sex = "MALE"
        elif dict1['CaseSex'] == 1:
            correct_sex = "FEMALE"
        else: print(f"Interview {interview['_id']} has error CaseSex value {dict1['CaseSex']}.")
        system = prompt.replace("{SEX}", correct_sex)
        user_inputs = interview['post_note_inputs']
        user_input = f"<summary>{user_inputs['Summary Statement']}</summary> \n<assessment>{user_inputs['Assessment']}</assessment> \n<plan>{user_inputs['Plan']}</plan>"
        # print(user_input + "\n") # debugging
        # Get all variable values that need AI
        prefill = "<thinking>Let me analyze each variable:\n\nCorrectSexID:"
        LLM_response = FEEDBACK_CLIENT.messages.create(
                    model=FEEDBACK_MODEL,
                    temperature=FEEDBACK_TEMP,
                    max_tokens=4096,
                    system=system,
                    messages=[
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": prefill}
                    ]
                )
        LLM_output = prefill + LLM_response.content[0].text
        thinking_start = LLM_output.find("<thinking>")
        thinking_end = LLM_output.find("</thinking>")
        answer_start = LLM_output.find("<answer>")
        answer_end = LLM_output.find("</answer>")
        if -1 in [thinking_start, thinking_end, answer_start, answer_end]: # wrong output format
            print("ERROR OUTPUT: " + LLM_output)
            continue
        thinking = LLM_output[thinking_start + len("<thinking>"):thinking_end].strip()
        answer = LLM_output[answer_start + len("<answer>"):answer_end].strip()
        dict2 = json.loads(answer)
        print(dict2)
        # Combine dicts
        combined = dict1 | dict2
        # print(thinking)
        # print(dict2) # debugging

        # times = {v: k for k, v in interview['times'].items()}
        # # InterviewLength
        # combined['InterviewLength'] = elapsed_minutes(times['start'], times['end_interview'])
        # # WriteupLength
        # combined['WriteupLength'] = elapsed_minutes(times['end_interview'], times['get_feedback'])

        # ResponsesExchanged
        combined['ResponsesExchanged'] = len(interview['messages']) // 2

        combined['thinking'] = thinking # add thinking on at very end

        # Save to DB
        target.insert_one(combined)

        # print("Completed!") # debugging
        
        # if StudentID == 3: break # test with first 3
    
    print(f"Number of unique students: {len(student_list)}")

import pandas as pd
from bson import ObjectId
def save_to_excel():
    client = MongoClient(DB_URI)
    source1 = client['Research']['Data.M1']
    source2 = client['Research']['Data.M2']
    docs1 = list(source1.find())
    docs2 = list(source2.find())

    df1 = pd.DataFrame(docs1)
    df2 = pd.DataFrame(docs2)

    # Remove unwanted columns from both DataFrames
    columns_to_remove = ['_id', 'interview_id', 'thinking']
    df1 = df1.drop(columns=[col for col in columns_to_remove if col in df1.columns])
    df2 = df2.drop(columns=[col for col in columns_to_remove if col in df2.columns])

    output_file = "research_data.xlsx"
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df1.to_excel(writer, sheet_name='Data_M1', index=False)
        df2.to_excel(writer, sheet_name='Data_M2', index=False)

def fix_times():
    client = MongoClient(DB_URI)
    interviews = client['Benchmark']['Interviews.M2']
    source = client['Research']['Data.M2_thinking']
    target = client['Research']['Data.M2_fixed']
    docs = list(source.find())

    for doc in docs:
        interview = interviews.find_one({'_id': doc['interview_id']})
        times = list(interview['times'].items())
        InterviewLength = 0
        WriteupLength = 0
        prev = None
        rec_int = False
        rec_post = False
        for i, time in enumerate(times):
            iso, check = time
            if check == 'start': 
                rec_int = True
                prev = iso
            if check == 'end_interview' and rec_int:
                InterviewLength += elapsed_minutes(prev, iso) # prev -> end_interview
                rec_int = False
                prev = iso
                rec_post = True
            if check == 'get_feedback' and rec_post:
                WriteupLength += elapsed_minutes(prev, iso) # prev -> get_feedback
                rec_post = False
            if check == 'continue':
                if rec_int and times[i-1][1] == "save_interview":
                    InterviewLength += elapsed_minutes(prev, times[i-1][0]) # prev -> recent save
                if rec_post and times[i-1][1] == "save_postnote":
                    WriteupLength += elapsed_minutes(prev, times[i-1][0]) # prev -> recent save
                prev = iso
        
        doc['InterviewLength'] = InterviewLength
        doc['WriteupLength'] = WriteupLength
        target.insert_one(doc)


def transfer_data():
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Group_Eval.M2_test']
    target = client['Backup']['Group.M2_test']
    docs = list(source.find())
    
    target.insert_many(docs)

    # for doc in docs:
    #     doc['sim_info'] = doc.pop("interview_info")
    #     doc['evaluation'] = doc.pop("feedback")
    #     source.replace_one({"_id": doc['_id']}, doc)

def edit_data():
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Interviews.M2_test']
    docs = list(source.find())

    source.update_many(
        {},  # Empty filter means all documents
        {"$unset": {
            "post_note_inputs.HPI": "",
            "post_note_inputs.Past Histories": ""
        }}
    )


def export_group_evals():
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Group_Eval.M2_test']
    docs = list(source.find())

    to_export = []
    for doc in docs:
        eval = {
            'sim_info': doc['sim_info'],
            'evaluation': doc['evaluation']
        }
        eval['sim_info'].pop('_id')
        to_export.append(eval)

    with open("./IDEA/benchmark/group_evals.json", 'w') as export_file:
        json.dump(to_export, export_file, indent=2)


if __name__ == "__main__":
    transfer_data()