import warnings
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent")

import sys
import os
import copy
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lookups import *
# from evaluate import *


# with open("./IDEA/benchmark/group_evals.json", 'r') as correct_file:
#     CORRECT_EVALS = json.loads(correct_file)

client = MongoClient(DB_URI)
group_eval_source = client['Benchmark']['Group_Eval.M2_test']
AI_EVALS = list(client['Benchmark']['AI_Eval.M2_test_flag_5'].find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))
HUMAN_EVALS = list(client['Benchmark']['Human_Eval.M2_test_copy'].find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))
# ALL_EVALS = AI_EVALS + HUMAN_EVALS

results = {}

example = AI_EVALS[0]
temp = {
    'All features': {'correct': 0, 'total': 0},
    'All scores': {'correct': 0, 'total': 0}
}
for part in example['evaluation']:
    temp[f"{part} features"] = {'correct': 0, 'total': 0}
    for feature in example['evaluation'][part]['features']:
        temp[f"{part} {feature}"] = {'correct': 0, 'total': 0}
    temp[f"{part} score"] = {'correct': 0, 'total': 0}

for eval in HUMAN_EVALS:
    if eval['username'] not in results:
        # temp = {
        #     'all': {'correct': 0, 'total': 0},
        #     # 'incorrect': []
        # }
        # for part in ["Summary Statement", 
        #              "Differential Diagnosis", 
        #              "Explanation of Lead Diagnosis", 
        #              "Explanation of Alternative Diagnoses", 
        #              "Plan"]:
        #     temp[part] = {'correct': 0, 'total': 0}
        # # for feature in ["A", "B", "C"]:
        # #     temp["Explanation of Lead Diagnosis"][feature] = 0
        results[eval['username']] = copy.deepcopy(temp)

    result = results[eval['username']]
    
    group_eval = group_eval_source.find_one({
        'sim_info.netid': eval['sim_info']['netid'], 
        'sim_info.patient': eval['sim_info']['patient']
        })
    
    for section in group_eval['evaluation']:
        for part in group_eval['evaluation'][section]:
            correct_features = group_eval['evaluation'][section][part]['features']
            correct_score = group_eval['evaluation'][section][part]['score']

            for feature, grade in eval['evaluation'][section][part]['features'].items():
                result[f"{part} {feature}"]['total'] += 1
                result[f"{part} features"]['total'] += 1
                result['All features']['total'] += 1
                if correct_features[feature] not in [True, False]:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {correct_features[feature]} is unexpected correct value.")
                elif correct_features[feature] == True and grade == True:
                    result[f"{part} {feature}"]['correct'] += 1
                    result[f"{part} features"]['correct'] += 1
                    result['All features']['correct'] += 1
                elif correct_features[feature] == False and grade == False:
                    result[f"{part} {feature}"]['correct'] += 1
                    result[f"{part} features"]['correct'] += 1
                    result['All features']['correct'] += 1
            
            result[f"{part} score"]['total'] += 1
            result["All scores"]['total'] += 1
            if eval['evaluation'][section][part]['score'] == correct_score:
                result[f"{part} score"]['correct'] += 1
                result["All scores"]['correct'] += 1


for eval in AI_EVALS:
    if eval['username'] not in results:
        # temp = {
        #     'all': {'correct': 0, 'total': 0},
        #     # 'incorrect': []
        # }
        # for part in ["Summary Statement", 
        #              "Differential Diagnosis", 
        #              "Explanation of Lead Diagnosis", 
        #              "Explanation of Alternative Diagnoses", 
        #              "Plan"]:
        #     temp[part] = {'correct': 0, 'total': 0}
        # # for conf in ["high", "medium", "low"]:
        # #     temp[conf] = {'correct': 0, 'total': 0}
        results[eval['username']] = copy.deepcopy(temp)
        for flag in ["flag", "noflag"]:
            results[eval['username']][flag] = {'correct': 0, 'total': 0}

    result = results[eval['username']]
    
    group_eval = group_eval_source.find_one({
        'sim_info.netid': eval['sim_info']['netid'], 
        'sim_info.patient': eval['sim_info']['patient']
        })
    
    for section in group_eval['evaluation']:
        for part in group_eval['evaluation'][section]:
            correct_features = group_eval['evaluation'][section][part]['features']
            correct_score = group_eval['evaluation'][section][part]['score']

            for feature, grading in eval['evaluation'][part]['features'].items():
                if 'grade' not in grading:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {grading}")
                grade = grading['grade']
                # conf = grading['confidence']
                if grading['flag'] == True:
                    flag = "flag"
                else:
                    flag = "noflag"

                result[f"{part} {feature}"]['total'] += 1
                result[f"{part} features"]['total'] += 1
                result['All features']['total'] += 1
                result[flag]['total'] += 1
                if feature not in correct_features:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {feature} is unexpected feature value.")
                if correct_features[feature] not in [True, False]:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {correct_features[feature]} is unexpected correct value.")
                elif correct_features[feature] == True and grade == True:
                    result[f"{part} {feature}"]['correct'] += 1
                    result[f"{part} features"]['correct'] += 1
                    result['All features']['correct'] += 1
                    result[flag]['correct'] += 1
                elif correct_features[feature] == False and grade == False:
                    result[f"{part} {feature}"]['correct'] += 1
                    result[f"{part} features"]['correct'] += 1
                    result['All features']['correct'] += 1
                    result[flag]['correct'] += 1
            
            result[f"{part} score"]['total'] += 1
            result["All scores"]['total'] += 1
            if "score" in eval['evaluation'][part]:
                score = eval['evaluation'][part]['score']
            else:
                score = eval['evaluation'][part]['scoring']['score']
            if score == correct_score:
                result[f"{part} score"]['correct'] += 1
                result["All scores"]['correct'] += 1


for username in results:
    print(f"----- {username} -----")
    for cat, result in results[username].items():
        print(f"{cat}: {result['correct']}/{result['total']} -> {result['correct']/result['total']}")
    print("\n")

# for conf in ["high", "medium", "low"]:
#     result = results["anthropic/claude-sonnet-4.5"][conf]
#     print(f"{conf}: {result['correct']}/{result['total']} -> {result['correct']/result['total']}")

# for flag in ["flag", "noflag"]:
#     print(f"{flag}:")
#     for username in ["anthropic/claude-sonnet-4.5", "openai/gpt-5", "anthropic/claude-haiku-4.5"]:
#         result = results[username][flag]
#         print(f"{username}: {result['correct']}/{result['total']} -> {result['correct']/result['total']}")


# def fmt_cell(res):
#     total = res.get('total', 0)
#     correct = res.get('correct', 0)
#     acc = round(correct / total, 4) if total else 0.0
#     percent = acc * 100
#     return f"{correct}/{total} -> {percent:.2f}%"

# # Collect the union of all dimensions (rows) across users, preserving a sensible order
# seen = set()
# all_dims = []

# for user, dims in results.items():
#     for dim in dims.keys():
#         if dim not in seen:
#             seen.add(dim)
#             all_dims.append(dim)

# # Optional: prioritize common top-level rows
# dims = [d for d in all_dims]

# # Build a DataFrame: columns = usernames, rows = dimensions
# usernames = sorted(results.keys())
# data = {
#     user: [
#         fmt_cell(results[user].get(dim, {'correct': 0, 'total': 0}))
#         for dim in dims
#     ]
#     for user in usernames
# }

# df = pd.DataFrame(data, index=dims)

# # Write to Excel
# output_path = "IDEA/benchmark/data/eval_data_11-17-25.xlsx"
# with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
#     df.to_excel(writer, sheet_name="Accuracy")