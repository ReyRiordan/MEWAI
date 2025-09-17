import time
from datetime import datetime
from docx import Document
import io
import os
import streamlit as st
import streamlit.components.v1 as components
# import streamlit_authenticator as auth
import base64
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
    st.session_state["stage"] = LOGIN_PAGE

def set_stage(stage):
    st.session_state["stage"] = stage


# DB SETUP
@st.cache_resource
def init_connection():
    return MongoClient(DB_URI)

DB_CLIENT = init_connection()
COLLECTION_INTERVIEWS = DB_CLIENT['Benchmark']['Interviews.M2_test']
COLLECTION_EVALS_HUMAN = DB_CLIENT['Benchmark']['Human_Eval.M2_test']
COLLECTION_EVALS_AI = DB_CLIENT['Benchmark']['AI_Eval.M2_test']
COLLECTION_EVALS_GROUP = DB_CLIENT['Benchmark']['Group_Eval.M2_test']

EVALUATORS_HUMAN = ['Fac1', 'Fac2', 'Fac3']
# EVALUATORS_AI = ['Claude 4S', 'GPT 5', 'Gemini 2.5P']
EVALUATORS_AI = ['Claude 4S']
EVALUATORS_GROUP = ['Group']

# OTHER
def load_and_setup():
    # Load the current interview based on view_index
    interview_id = st.session_state["interview_list"][st.session_state["current_index"]]["_id"]
    interview = COLLECTION_INTERVIEWS.find_one({"_id": interview_id})

    # Load evals
    evaluations = {}
    for evaler in EVALUATORS_HUMAN + EVALUATORS_AI + EVALUATORS_GROUP:
        evaluations[evaler] = None
    eval_list_human = list(COLLECTION_EVALS_HUMAN.find({'sim_info._id': interview_id}))
    eval_list_ai = list(COLLECTION_EVALS_AI.find({'sim_info._id': interview_id}))
    eval_list_group = list(COLLECTION_EVALS_GROUP.find({'sim_info._id': interview_id}))
    eval_list = eval_list_human + eval_list_ai + eval_list_group
    for eval in eval_list:
        if eval['username'] in evaluations:
            evaluations[eval['username']] = eval

    return interview, evaluations


if st.session_state["stage"] == LOGIN_PAGE:
    layout1 = st.columns([2, 3, 2])
    with layout1[1]:
        st.title("MEWAI: View/Compare Evaluations")
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
                    set_stage(VIEW_EVAL)
                    st.rerun()
                else:
                    st.write("Password incorrect.")


if st.session_state["stage"] == VIEW_EVAL:
    st.title("View Evaluations")
    layout1 = st.columns([2, 3, 2])

    # Initialize data if needed
    if "interview_list" not in st.session_state:
        st.session_state["interview_list"] = list(COLLECTION_INTERVIEWS.find({}, {"netid": 1, "patient": 1}))
        st.session_state["interviews_label:index"] = {}
        for index, interview in enumerate(st.session_state["interview_list"]):
            label = interview["netid"] + ": " + interview["patient"]
            st.session_state["interviews_label:index"][label] = index
        st.session_state["current_index"] = None
        st.session_state["current_evaluation"] = None

    # Selectbox section
    layout11 = layout1[1].columns([1, 2, 1])
    
    # Function for selectbox change
    def on_select_change():
        # Get the new index from the selected label
        st.session_state["current_index"] = st.session_state["interviews_label:index"][st.session_state["selected"]]
        
    # Create the selectbox
    layout11[1].selectbox(
        "Select an interview:", 
        options=st.session_state["interviews_label:index"],
        index=st.session_state["current_index"],
        placeholder="Select Interview", 
        label_visibility="collapsed", 
        key="selected",
        on_change=on_select_change
    )

    if st.session_state["current_index"] is not None:
        # Load/setup current interview and evaluation as needed
        interview, evaluations = load_and_setup()
        display_comparison(interview, evaluations)
    
    # Function to handle dropdown navigation
    def navigate(direction):
        if direction == "next":
            st.session_state["current_index"] = min(len(st.session_state["interview_list"]) - 1, 
                                              st.session_state["current_index"] + 1)
        elif direction == "back":
            st.session_state["current_index"] = max(0, st.session_state["current_index"] - 1)

        st.session_state['started_time'] = False

    if st.session_state["current_index"] is not None:
        # Top navigation buttons
        if layout11[0].button("Back", use_container_width=True, key="backtop"):
            navigate("back")
            st.rerun()
        if layout11[2].button("Next", use_container_width=True, key="nexttop"):
            navigate("next")
            st.rerun()

    