import warnings
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent")

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lookups import *
# from evaluate import *


# with open("./IDEA/benchmark/group_evals.json", 'r') as correct_file:
#     CORRECT_EVALS = json.loads(correct_file)

client = MongoClient(DB_URI)
group_eval_source = client['Benchmark']['Group_Eval.M2_test']
AI_EVALS = list(client['Benchmark']['AI_Eval.M2_test_flag'].find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))
HUMAN_EVALS = list(client['Benchmark']['Human_Eval.M2_test_copy'].find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))
# ALL_EVALS = AI_EVALS + HUMAN_EVALS

results = {}

for eval in HUMAN_EVALS:
    if eval['username'] not in results:
        temp = {
            'all': {'correct': 0, 'total': 0},
            # 'incorrect': []
        }
        for part in ["Summary Statement", 
                     "Differential Diagnosis", 
                     "Explanation of Lead Diagnosis", 
                     "Explanation of Alternative Diagnoses", 
                     "Plan"]:
            temp[part] = {'correct': 0, 'total': 0}
        # for feature in ["A", "B", "C"]:
        #     temp["Explanation of Lead Diagnosis"][feature] = 0
        results[eval['username']] = temp

    result = results[eval['username']]
    
    group_eval = group_eval_source.find_one({
        'sim_info.netid': eval['sim_info']['netid'], 
        'sim_info.patient': eval['sim_info']['patient']
        })
    
    for section in eval['evaluation']:
        for part in eval['evaluation'][section]:
            correct_features = group_eval['evaluation'][section][part]['features']
            for feature, grade in eval['evaluation'][section][part]['features'].items():
                result[part]['total'] += 1
                result['all']['total'] += 1
                if correct_features[feature] not in [True, False]:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {correct_features[feature]} is unexpected correct value.")
                elif correct_features[feature] == True and grade == True:
                    result[part]['correct'] += 1
                    result['all']['correct'] += 1
                    # if part == "Explanation of Lead Diagnosis":
                    #     result[part][feature] += 1
                elif correct_features[feature] == False and grade == False:
                    result[part]['correct'] += 1
                    result['all']['correct'] += 1
                    # if part == "Explanation of Lead Diagnosis":
                    #     result[part][feature] += 1

for eval in AI_EVALS:
    if eval['username'] not in results:
        temp = {
            'all': {'correct': 0, 'total': 0},
            # 'incorrect': []
        }
        for part in ["Summary Statement", 
                     "Differential Diagnosis", 
                     "Explanation of Lead Diagnosis", 
                     "Explanation of Alternative Diagnoses", 
                     "Plan"]:
            temp[part] = {'correct': 0, 'total': 0}
        # for conf in ["high", "medium", "low"]:
        #     temp[conf] = {'correct': 0, 'total': 0}
        for flag in ["flag", "noflag"]:
            temp[flag] = {'correct': 0, 'total': 0}
        results[eval['username']] = temp

    result = results[eval['username']]
    
    group_eval = group_eval_source.find_one({
        'sim_info.netid': eval['sim_info']['netid'], 
        'sim_info.patient': eval['sim_info']['patient']
        })
    
    for section in group_eval['evaluation']:
        for part in group_eval['evaluation'][section]:
            correct_features = group_eval['evaluation'][section][part]['features']
            for feature, grading in eval['evaluation'][part]['features'].items():
                if 'grade' not in grading:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {grading}")
                grade = grading['grade']
                # conf = grading['confidence']
                if grading['flag'] == True:
                    flag = "flag"
                else:
                    flag = "noflag"

                result[part]['total'] += 1
                # result[conf]['total'] += 1
                result[flag]['total'] += 1
                result['all']['total'] += 1
                if feature not in correct_features:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {feature} is unexpected feature value.")
                if correct_features[feature] not in [True, False]:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {correct_features[feature]} is unexpected correct value.")
                elif correct_features[feature] == True and grade == True:
                    result[part]['correct'] += 1
                    # result[conf]['correct'] += 1
                    result[flag]['correct'] += 1
                    result['all']['correct'] += 1
                elif correct_features[feature] == False and grade == False:
                    result[part]['correct'] += 1
                    # result[conf]['correct'] += 1
                    result[flag]['correct'] += 1
                    result['all']['correct'] += 1

                
for cat, result in results["Fac1"].items():
    print(f"{cat}:")
    for username in results:
        result = results[username][cat]
        print(f"{username}: {result['correct']}/{result['total']} -> {result['correct']/result['total']}")
    print("\n")

# for conf in ["high", "medium", "low"]:
#     result = results["anthropic/claude-sonnet-4.5"][conf]
#     print(f"{conf}: {result['correct']}/{result['total']} -> {result['correct']/result['total']}")

for flag in ["flag", "noflag"]:
    print(f"{flag}:")
    for username in ["anthropic/claude-sonnet-4.5", "openai/gpt-5", "anthropic/claude-haiku-4.5"]:
        result = results[username][flag]
        print(f"{username}: {result['correct']}/{result['total']} -> {result['correct']/result['total']}")