import json
import os

transcript_path = r"C:\Users\eluithi\.gemini\antigravity\brain\10e29165-0493-42e0-80b7-830ecdfb89d7\.system_generated\logs\transcript_full.jsonl"
output_path = r"E:\POLYDIM_EINSOF\REPORTES\glm_5_3_red_team_dump_raw.md"

os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(transcript_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the last USER_INPUT that is massive (contains @page and GLM-5.3 stuff)
for line in reversed(lines):
    try:
        data = json.loads(line)
        if data.get('type') == 'USER_INPUT' and 'content' in data:
            content = data['content']
            if '@page { size: 21cm 29.7cm;' in content or 'GLM' in content or 'V109' in content:
                print(f"Found massive user dump, length: {len(content)}")
                with open(output_path, 'w', encoding='utf-8') as out:
                    out.write(content)
                print(f"Saved to {output_path}")
                break
    except Exception as e:
        print(f"Error parsing line: {e}")
