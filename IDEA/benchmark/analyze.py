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


if __name__ == "__main__":
    client = MongoClient(DB_URI)
    source = client['Benchmark']['Group_Eval.M2_test']
    compute_time_spent(source)