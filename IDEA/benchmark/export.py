from datetime import datetime
from docx import Document
import os
from pymongo.mongo_client import MongoClient
import pandas as pd
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv('.venv/.env')
DB_URI = os.getenv("DB_URI")


def export_to_excel_old(output_file: str):
    client = MongoClient(DB_URI)
    source1 = client['Benchmark']['AI_Eval.M2_test']
    source2 = client['Benchmark']['Human_Eval.M2_test']
    query = {"username": 1,
             "sim_info": 1,
             "time_spent": 1,
             "evaluation": 1}
    docs1 = list(source1.find({}, query))
    docs2 = list(source2.find({}, query))
    docs = docs2 + docs1 # human first ig
    
    summary_list = []
    diff_list = []
    exlead_list = []
    exalt_list = []
    plan_list = []

    for doc in docs:
        if doc['username'] == "admin": continue

        current_dict = {"_id": doc['_id'], 
                        "username": doc['username'], 
                        "netid": doc['sim_info']['netid'], 
                        "patient": doc['sim_info']['patient'], 
                        "time_spent": doc['time_spent']}
        
        eval = doc['evaluation']

        def extract_grades(eval_part: dict) -> dict:
            grades_dict = eval_part['features']
            grades_dict['score'] = eval_part['score']
            return grades_dict
        
        summary = current_dict.copy()
        summary_grades = extract_grades(eval['Summary Statement']['Summary Statement'])
        summary.update(summary_grades)
        summary_list.append(summary)

        diff = current_dict.copy()
        diff_grades = extract_grades(eval['Assessment']['Differential Diagnosis'])
        diff.update(diff_grades)
        diff_list.append(diff)

        exlead = current_dict.copy()
        exlead_grades = extract_grades(eval['Assessment']['Explanation of Lead Diagnosis'])
        exlead.update(exlead_grades)
        exlead_list.append(exlead)

        exalt = current_dict.copy()
        exalt_grades = extract_grades(eval['Assessment']['Explanation of Alternative Diagnoses'])
        exalt.update(exalt_grades)
        exalt_list.append(exalt)

        plan = current_dict.copy()
        plan_grades = extract_grades(eval['Plan']['Plan'])
        plan.update(plan_grades)
        plan_list.append(plan)

    for to_sort in [summary_list, diff_list, exlead_list, exalt_list, plan_list]:
        to_sort.sort(key=lambda x: (x.get('netid', ''), x.get('username', '')))

    df_summary = pd.DataFrame(summary_list)     
    df_diff = pd.DataFrame(diff_list)
    df_exlead = pd.DataFrame(exlead_list) 
    df_exalt = pd.DataFrame(exalt_list)
    df_plan = pd.DataFrame(plan_list)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Summary Statement', index=False)
        df_diff.to_excel(writer, sheet_name='Differential Diagnosis', index=False)
        df_exlead.to_excel(writer, sheet_name='Lead Diagnosis', index=False)
        df_exalt.to_excel(writer, sheet_name='Alternative Diagnoses', index=False)
        df_plan.to_excel(writer, sheet_name='Plan', index=False)

    client.close()

def export_to_excel(output_file: str):
    client = MongoClient(DB_URI)
    source1 = client['Benchmark']['AI_Eval.M2_test']
    source2 = client['Benchmark']['Human_Eval.M2_test']
    source3 = client['Benchmark']['Group_Eval.M2_test']
    query = {"username": 1,
             "sim_info": 1,
             "time_spent": 1,
             "evaluation": 1}
    docs1 = list(source1.find({}, query))
    docs2 = list(source2.find({}, query))
    docs3 = list(source3.find({}, query))
    docs = docs2 + docs3 + docs1 # order? human -> group -> AI
    
    master_dict = {}

    for doc in docs:
        if doc['username'] == "admin": continue
        
        sim_id = doc['sim_info']['_id']
        if sim_id not in master_dict:
            master_dict[sim_id] = {
                "sim_id": doc['sim_info']['_id'], 
                "netid": doc['sim_info']['netid'], 
                "patient": doc['sim_info']['patient'], 
            }
        current_dict = master_dict[sim_id]
        
        eval = doc['evaluation']

        def extract_grades(eval_part: dict, prefix: str) -> dict:
            grades_dict = {}
            for key, value in eval_part['features'].items():
                grades_dict[prefix + key] = 1 if value else 0
            grades_dict[prefix + 'score'] = eval_part['score']
            # grades_dict[prefix + 'comment'] = eval_part['comment']
            return grades_dict
        
        pre = doc['username']
        if pre == "anthropic/claude-sonnet-4.5":
            pre = "AI"
        
        summary_grades = extract_grades(eval['Summary Statement']['Summary Statement'], f"{pre}_sum_")
        current_dict.update(summary_grades)

        diff_grades = extract_grades(eval['Assessment']['Differential Diagnosis'], f"{pre}_diff_")
        current_dict.update(diff_grades)

        exlead_grades = extract_grades(eval['Assessment']['Explanation of Lead Diagnosis'], f"{pre}_exlead_")
        current_dict.update(exlead_grades)

        exalt_grades = extract_grades(eval['Assessment']['Explanation of Alternative Diagnoses'], f"{pre}_exalt_")
        current_dict.update(exalt_grades)

        plan_grades = extract_grades(eval['Plan']['Plan'], f"{pre}_plan_")
        current_dict.update(plan_grades)

    master_list = list(master_dict.values())

    df = pd.DataFrame(master_list)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='ALL', index=False)

    client.close()


if __name__ == "__main__":
    export_to_excel("IDEA/benchmark/data/eval_data_10-20-25.xlsx")