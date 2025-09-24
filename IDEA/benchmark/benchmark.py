import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lookups import *
from evaluate import *


# with open("./IDEA/benchmark/group_evals.json", 'r') as correct_file:
#     CORRECT_EVALS = json.loads(correct_file)

client = MongoClient(DB_URI)
group_eval_source = client['Benchmark']['Group_Eval.M2_test']
AI_EVALS = list(client['Benchmark']['AI_Eval.M2_test'].find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))
HUMAN_EVALS = list(client['Benchmark']['Human_Eval.M2_test_copy'].find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))
ALL_EVALS = AI_EVALS + HUMAN_EVALS

results = {}
for eval in ALL_EVALS:
    if eval['username'] not in results:
        results[eval['username']] = {
            'n_correct': 0,
            'n_total': 0,
            'incorrect': []
        }
    result = results[eval['username']]
    
    group_eval = group_eval_source.find_one({
        'sim_info.netid': eval['sim_info']['netid'], 
        'sim_info.patient': eval['sim_info']['patient']
        })
    
    for section in eval['evaluation']:
        for part in eval['evaluation'][section]:
            correct_features = group_eval['evaluation'][section][part]['features']
            for feature, grade in eval['evaluation'][section][part]['features'].items():
                result['n_total'] += 1
                if correct_features[feature] not in ["TRUE", "FALSE", "EITHER"]:
                    print(f"ERROR @ netid {eval['sim_info']['netid']}, patient {eval['sim_info']['patient']}: {correct_features[feature]} is unexpected correct value.")
                elif correct_features[feature] == "TRUE" and grade == True:
                    result['n_correct'] += 1
                elif correct_features[feature] == "FALSE" and grade == False:
                    result['n_correct'] += 1
                elif correct_features[feature] == "EITHER":
                    result['n_correct'] += 1

for username, result in results.items():
    print(f"{username}: {result['n_correct']}/{result['n_total']} -> {result['n_correct']/result['n_total']}")