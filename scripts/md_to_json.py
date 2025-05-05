import re
import json
from pathlib import Path

def parse_markdown(md_path):
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    questions = []
    q = {}
    options = {}
    pattern_question = re.compile(r"^###\s*(\d+)\.\s*(.+)")
    pattern_option = re.compile(r"^- \(([A-D])\)\s*(.+)")
    pattern_answer = re.compile(r"^✅\s*正解：(.+)")

    for line in lines:
        line = line.strip()

        if match := pattern_question.match(line):
            if q:
                q["options"] = options
                questions.append(q)
                q, options = {}, {}
            q["id"] = int(match.group(1))
            q["question"] = match.group(2)

        elif match := pattern_option.match(line):
            options[match.group(1)] = match.group(2)

        elif match := pattern_answer.match(line):
            ans_raw = match.group(1).strip()
            if re.fullmatch(r"[A-D](,[A-D])*", ans_raw):  # 多個答案
                q["answer"] = ans_raw.split(",")
            elif ans_raw in ["送分", "給分", "無正解"]:
                q["answer"] = None  # 或改為 q["note"] = "送分"
            else:
                q["answer"] = ans_raw  # 正常單一答案

    if q:
        q["options"] = options
        questions.append(q)

    return questions

# 批次轉換 merged_exam_with_figure/*.md → DataSet/*.json
input_dir = Path("merged_exam_with_figure")
output_dir = Path("DataSet")
output_dir.mkdir(exist_ok=True)

for md_file in input_dir.glob("*.md"):
    data = parse_markdown(md_file)
    json_filename = md_file.stem + ".json"
    output_path = output_dir / json_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ {md_file.name} → {output_path.name}，共 {len(data)} 題")
