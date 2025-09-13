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
import emoji
import string


# STREAMLIT SETUP
st.set_page_config(page_title = "MEWAI",
                   page_icon = "🧑‍⚕️",
                   layout = "wide",
                   initial_sidebar_state="collapsed")

if "stage" not in st.session_state:
    st.session_state["stage"] = "LOGIN_PAGE"

def set_stage(stage):
    st.session_state["stage"] = stage


# DB SETUP
@st.cache_resource
def init_connection():
    return MongoClient(DB_URI)

DB_CLIENT = init_connection()
SIMS_TEST = DB_CLIENT["Benchmark"]["Interviews.M2_test"]
SIMS_REM = DB_CLIENT['Benchmark']['Interviews.M2_rem']
EVALS_TEST = DB_CLIENT["Benchmark"]["Human_Eval.M2_test"]
EVALS_REM = DB_CLIENT['Benchmark']['Human_Eval.M2_rem']


def update_evaluation(checkpoint: str, evaluation: dict):
    """Update or insert an evaluation document in the database."""
    current_time = datetime.now().isoformat()
    evaluation['times'][current_time] = checkpoint
    query = {
        "username": st.session_state["username"],
        "sim_info._id": evaluation["sim_info"]["_id"]
    }
    st.session_state['db_evals'].replace_one(query, evaluation, upsert=True)

# OTHER
def load_and_setup():
    # Load the current sim based on view_index
    sim_id = st.session_state["sim_list"][st.session_state["current_index"]]["_id"]
    sim = st.session_state['db_sims'].find_one({"_id": sim_id})

    # Load or create the evaluation for this sim
    evaluation = st.session_state['db_evals'].find_one({"username": st.session_state["username"], "sim_info._id": sim_id})
    if not evaluation:
        evaluation = {
            "username": st.session_state["username"],
            "sim_info": st.session_state["sim_list"][st.session_state["current_index"]],
            "mark": "",
            "times": {}
        }
        # Initialize eval structure
        eval = {}
        for section in RUBRIC:
            eval[section] = {}
            for part in RUBRIC[section]:
                eval[section][part] = {'comment': None, 'features': {}, 'score': None}
                for letter in RUBRIC[section][part]['features'].keys():
                    eval[section][part]['features'][letter] = False
        evaluation["evaluation"] = eval

    # Insert if new, either way record start time
    if not st.session_state['started_time']:
        update_evaluation("start", evaluation)
        st.session_state['started_time'] = True

    return sim, evaluation


if st.session_state["stage"] == "LOGIN_PAGE":
    layout1 = st.columns([2, 3, 2])
    with layout1[1]:
        st.title("MEWAI: Human Evaluation")
        st.write("Thank you so much for your cooperation.")
        st.write("Please begin by logging in as you were directed. If you encounter any issues, please contact rhr58@scarletmail.rutgers.edu")

        username = st.text_input("Username:")
        if username and username not in EVALUATORS: 
            st.write("Invalid username.")
        st.session_state["admin"] = True if username == "admin" else False
        password = st.text_input("Password:", type = "password")

        layout12b = layout1[1].columns(5)
        if layout12b[2].button("Log in"):
            if username in EVALUATORS:
                correct = EVALUATORS[username]["password"]
                if username in EVALUATORS and password == correct:
                    st.session_state["username"] = username
                    st.write("Authentication successful!")
                    time.sleep(1)
                    set_stage("DATASET_SELECTION")
                    st.rerun()
                else:
                    st.write("Password incorrect.")


if st.session_state['stage'] == "DATASET_SELECTION":
    def select_db(selection: str):
        if selection == "test":
            st.session_state['db_sims'] = SIMS_TEST
            st.session_state['db_evals'] = EVALS_TEST
        elif selection == "rem":
            st.session_state['db_sims'] = SIMS_REM
            st.session_state['db_evals'] = EVALS_REM
        else:
            st.write("ERROR: INVALID SELECTION")
            return
        if st.session_state["username"] == "Group":
            set_stage("GROUP_EVAL")
        else:
            set_stage("HUMAN_EVAL")

    layout1 = st.columns([2, 3, 2])
    with layout1[1]:
        st.header("Select dataset to evaluate:")
        layout11 = st.columns([1, 1])
        layout11[0].button(
            "M2 Test (n=30)",
            on_click=select_db,
            args=["test"],
            use_container_width=True
        )
        layout11[1].button(
            "M2 Remainders (n=230)",
            on_click=select_db,
            args=["rem"],
            use_container_width=True
        )


if st.session_state["stage"] == "HUMAN_EVAL":
    st.title("Human Evaluation")
    with st.expander("**Directions (click to expand)**"):
        st.write("For each section of the post note, the student's response is displayed on the left. On the right side is a list of features for the rubric corresponding to that section - please grade their response by checking off the features it satisfies. Then, provide a detailed rationale for your grading in the comments box. NOTE: at least one section has multiple parts - please provide a score for each part.")
        st.write("Use the \"Back\", \"Next\", and dropdown selection box to navigate freely between notes.")
        st.write(emoji.emojize("Marking a note as done will mark it with a :white_check_mark: beside it in the dropdown. Flagging it will mark it with a :triangular_flag_on_post:."))
        st.write("Please note that you MUST press one of the buttons to save your progress (there is no auto-save), but all buttons including the dropdown selection will save.")
    layout1 = st.columns([2, 3, 2])

    # Update/initialize main lookup dict labels
    def update_label(evaluation, current_index):
        items = list(st.session_state["sims_label:index"].items())
        for label, index in items:
            if index == current_index: 
                old_label = label
                break
        sim = evaluation["sim_info"]
        eval_for_label = st.session_state['db_evals'].find_one({"username": evaluation["username"], "sim_info._id": sim["_id"]})
        new_label = sim["netid"] + ": " + sim["patient"] + " " + eval_for_label["mark"]
        new_label = emoji.emojize(new_label, language='alias')
        reconstruct = {}
        for label, index in items:
            if label == old_label:
                reconstruct[new_label] = index
            else:
                reconstruct[label] = index
        st.session_state["sims_label:index"] = reconstruct

    
    # Initialize data if needed
    if "sim_list" not in st.session_state:
        st.session_state["sim_list"] = list(st.session_state['db_sims'].find({}, {"netid": 1, "patient": 1}))
        st.session_state["sims_label:index"] = {}
        for index, sim in enumerate(st.session_state["sim_list"]):
            label = sim["netid"] + ": " + sim["patient"]
            eval_for_label = st.session_state['db_evals'].find_one({"username": st.session_state["username"], "sim_info._id": sim["_id"]})
            if eval_for_label:
                label += " " + eval_for_label["mark"]
                label = emoji.emojize(label, language='alias')
            st.session_state["sims_label:index"][label] = index
        st.session_state["current_index"] = None
        st.session_state["current_evaluation"] = None
        st.session_state['started_time'] = False

    layout11 = layout1[1].columns([1, 2, 1])
    
    def on_select_change():
        if st.session_state["current_evaluation"]:
            update_evaluation("end", st.session_state["current_evaluation"])
        # Get the new index from the selected label
        st.session_state["current_index"] = st.session_state["sims_label:index"][st.session_state["selected"]]
        st.session_state['started_time'] = False
        
    layout11[1].selectbox(
        "Select a simulation:", 
        options=st.session_state["sims_label:index"],
        index=st.session_state["current_index"],
        placeholder="Select Simulation", 
        label_visibility="collapsed", 
        key="selected",
        on_change=on_select_change
    )

    if st.session_state["current_index"] is not None:
        sim, evaluation = load_and_setup()
        st.session_state["current_evaluation"] = evaluation
        evaluation["evaluation"] = display_evaluation(sim, evaluation["evaluation"])
        st.session_state["current_evaluation"] = evaluation

    def navigate(direction):
        update_evaluation("end", st.session_state["current_evaluation"])
        if direction == "next":
            st.session_state["current_index"] = min(len(st.session_state["sim_list"]) - 1, 
                                              st.session_state["current_index"] + 1)
        elif direction == "back":
            st.session_state["current_index"] = max(0, st.session_state["current_index"] - 1)
        st.session_state['started_time'] = False

    def mark_evaluation(mark: str):
        st.session_state["current_evaluation"]["mark"] = mark
        update_evaluation("mark", st.session_state["current_evaluation"])
        update_label(st.session_state["current_evaluation"], st.session_state["current_index"])

    def save_evaluation():
        update_evaluation("save", st.session_state["current_evaluation"])
        
    if st.session_state["current_index"] is not None:
        if layout11[0].button("Back", use_container_width=True, key="backtop"):
            navigate("back")
            st.rerun()
        if layout11[2].button("Next", use_container_width=True, key="nexttop"):
            navigate("next")
            st.rerun()
        
        # Marking buttons
        layout12 = layout1[1].columns([1, 1, 1])
        if layout12[0].button(emoji.emojize("Flag :triangular_flag_on_post:"), use_container_width=True, key="flagtop"):
            mark_evaluation(":triangular_flag_on_post:")
            st.rerun()
        if layout12[1].button("Save", use_container_width=True, key="savetop"):
            save_evaluation()
            st.rerun()
        if layout12[2].button(emoji.emojize("Done :white_check_mark:"), use_container_width=True, key="donetop"):
            mark_evaluation(":white_check_mark:")
            st.rerun()


if st.session_state["stage"] == "GROUP_EVAL":
    