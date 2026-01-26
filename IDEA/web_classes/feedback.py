from lookups import *
import json
from openai import OpenAI
import pydantic 
from typing import Optional, List

from .patient import *
from .message import *
from web_methods.LLM import *
            
class Feedback(pydantic.BaseModel):

    info: Optional[dict]
    post_note: Optional[dict]

    @classmethod
    def restore_previous(cls, feedback: dict):
        return cls(feedback=feedback)
    
    @classmethod
    def build(cls, patient: Patient, messages: list[Message], post_note_inputs: dict[str, str], rubric_id=RUBRIC_ID):
        def create_prompt(prompt: str, rubric: dict) -> str:
            prompt = prompt.replace("{{title}}", rubric['title'])
            prompt = prompt.replace("{{desc}}", rubric['desc'])

            extracted_rubric = {
                "features": rubric['features'],
                "scoring": rubric['scoring']
            }
            prompt = prompt.replace("{{rubric}}", str(extracted_rubric))

            return prompt
        
        def extract_from_output(output_raw: str) -> dict:
            m = re.search(r"```json\s*(.*?)\s*```", output_raw, re.DOTALL)
            if m:
                output = m.group(1)
            else:
                output = output_raw.strip()
            
            try:
                output_dict = json.loads(output)
            except json.JSONDecodeError as e:
                print(f"ERROR: Could not parse grade JSON")
                print(output_raw)

            return output_dict
        
        def generate_evaluate_whatev(rubric: dict, user_input: str) -> dict:
            system_prompt = create_prompt(FEEDBACK_PROMPT, rubric)

            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {
                "model": FEEDBACK_MODEL,
                "reasoning":{"enabled": True},
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}]
            }
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            raw = requests.post(url, json=payload, headers=headers)
            raw = raw.json()
            print(raw)

            try:
                output = raw['choices'][0]['message']['content']
            except:
                raise ValueError()
            eval = extract_from_output(output) # features (rationale, grade, confidence), score
            print(eval)

            info['tokens']['input'] += raw['usage']['prompt_tokens']
            info['tokens']['output'] += raw['usage']['completion_tokens']

            thoughts = ""
            for feature in eval['features']:
                thoughts += f"{feature}: {eval['features'][feature]['rationale']}\n\n"
            thoughts += f"Score: {eval['scoring']['rationale']}"

            formatted = {
                "input": user_input,
                "comment": None,
                "thought": thoughts,
                "score": int(eval['scoring']['score']),
                "max": int(next(iter(rubric['scoring'])))
            }

            return formatted
    
        info = {
            'rubric_id': rubric_id, 
            'model': {
                'name': FEEDBACK_MODEL, 
                'temperature': FEEDBACK_TEMP, 
                # 'token_cost': COSTS[FEEDBACK_MODEL]
                }, 
            'tokens': {
                'input': 0, 
                'output': 0
            }
        }
        post_note = {}

        categories = ["Summary Statement", "Assessment", "Plan"]
        # sectioned = ["HPI", "Past Histories", "Assessment"]

        # Use info from source rubric + user input to generate/process/write feedback for specific section/part
        # def generate_process_write(source: dict, input: str):
        #     response = generate_feedback(title = source["title"],
        #                                  desc = source["desc"],
        #                                  rubric = source["rubric"],
        #                                  user_input = input, 
        #                                  tokens = info['tokens'])
        #     # split into feedback / thought process + final score
        #     split_attempt = response.strip().split("Thought process:")
        #     if len(split_attempt) == 2:
        #         comment, scoring = split_attempt
        #         # split into thought process / final score
        #         thought, score = scoring.split("FINAL SCORE: ")
        #         score = int(score)
        #     else: # error handling?
        #         comment = response
        #         thought = None
        #         score = 0
        #     output = {"input": input,
        #               "comment": comment,
        #               "thought": thought,
        #               "score": score,
        #               "max": source["points"]}
        #     return output

        assessment_parts = ["Differential Diagnosis", "Explanation of Lead Diagnosis", "Explanation of Alternative Diagnoses"]

        # Create feedback
        for category in categories:
            if category == "Assessment":
                post_note[category] = {}
                for part in assessment_parts:
                    post_note[category][part] = generate_evaluate_whatev(RUBRIC[part], post_note_inputs[category])
                    st.write(f"Section \"{part}\" complete.")
            else:
                post_note[category] = generate_evaluate_whatev(RUBRIC[category], post_note_inputs[category])
                st.write(f"Section \"{category}\" complete.")
        
        return cls(info=info, post_note=post_note)

        # self.data_acquisition = DataAcquisition(patient, messages)
        # self.diagnosis = Diagnosis(patient, user_diagnosis)