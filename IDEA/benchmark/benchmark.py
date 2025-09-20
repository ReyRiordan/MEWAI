import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lookups import *
from evaluate import *


# with open("./IDEA/benchmark/group_evals.json", 'r') as correct_file:
#     CORRECT_EVALS = json.loads(correct_file)

client = MongoClient(DB_URI)
group_eval_source = client['Benchmark']['Group_Eval.M2_test']
source = client['Benchmark']['AI_Eval.M2_test']
AI_EVALS = list(source.find({}, {'_id': 0, 'username': 1, 'model_info': 1, 'sim_info': 1, 'evaluation': 1}))


n_correct = 0
n_total = 0
for eval in AI_EVALS:
    group_eval = group_eval_source.find_one({
        'sim_info.netid': eval['sim_info']['netid'], 
        'sim_info.patient': eval['sim_info']['patient']
        })
    
    for section in eval['evaluation']:
        for part in eval['evaluation'][section]:
            correct_features = group_eval['evaluation'][section][part]['features']
            for feature, grade in eval['evaluation'][section][part]['features'].items():
                n_total += 1
                if correct_features[feature] not in ["TRUE", "FALSE", "EITHER"]:
                    print(f"ERROR: {correct_features[feature]} is unexpected correct value.")
                elif correct_features[feature] == "TRUE" and grade == True:
                    n_correct += 1
                elif correct_features[feature] == "FALSE" and grade == False:
                    n_correct += 1
                elif correct_features[feature] == "EITHER":
                    n_correct += 1

print(f"Accuracy: {n_correct}/{n_total} -> {n_correct/n_total}")