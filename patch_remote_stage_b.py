import re
import sys

file_path = "/opt/dias/src/stages/stage_b_semantic_analyzer.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to find where response_text is assigned
target_pattern = r'(\s+)(response_text = response\["output"\]\.get\("text", ""\))(.*?)(\n\s+else:)'
# We want to replace the block with the new saving logic
replacement = r'''\g<1>raw_resp = response["output"].get("text", "")
\g<1>dump_dir = self.persistence.project_root / "stages" / "stage_b" / "raw_dumps"
\g<1>dump_dir.mkdir(parents=True, exist_ok=True)
\g<1>dump_path = dump_dir / f"{block_id}_raw.txt"
\g<1>try:
\g<1>    with open(dump_path, "w", encoding="utf-8") as f:
\g<1>        f.write(raw_resp)
\g<1>except Exception as e:
\g<1>    self.logger.error(f"Failed to save raw dump: {e}")
\g<1>
\g<1># Read back from the saved file as requested
\g<1>try:
\g<1>    with open(dump_path, "r", encoding="utf-8") as f:
\g<1>        response_text = f.read()
\g<1>except Exception:
\g<1>    response_text = raw_resp\g<4>'''

new_content = re.sub(target_pattern, replacement, content, flags=re.DOTALL)

if new_content != content:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Patch applicata con successo sul server.")
else:
    print("Nessuna modifica effettuata (il pattern non ha fatto match).")
