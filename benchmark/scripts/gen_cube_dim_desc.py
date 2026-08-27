"""PoC: sample data + schema -> LLM -> bilingual descriptions for Cube dims."""
import json, os, sqlite3, sys
sys.path.insert(0, '/Users/zm/Code/Datus-agent')

DB = '/Users/zm/.datus/benchmark/bird/dev_20240627/dev_databases/california_schools/california_schools.sqlite'
con = sqlite3.connect(DB)

def samples(col, n=8):
    rows = con.execute(
        f'SELECT DISTINCT "{col}" FROM schools WHERE "{col}" IS NOT NULL AND TRIM("{col}")<>"" '
        f'ORDER BY RANDOM() LIMIT {n}').fetchall()
    return [str(r[0])[:40] for r in rows]

SYSTEM = """你是数据语义建模专家。根据表用途、字段名和真实抽样值，为 BI 语义层维度写描述。
输出仅 JSON：{"description": "英文描述(含取值含义解释与常见别名)", "aliases": ["别名1", ...], "zh": "一句话中文含义"}
要求：编码型字段必须解读代码含义；枚举型说明每个值；aliases 中英都要有。"""

TARGETS = ["Charter", "Virtual", "Magnet", "StatusType", "FundingType", "SOCType"]
out = {}
for col in TARGETS:
    ss = samples(col)
    user = f"Table: california K-12 public schools\nColumn: {col}\nSample distinct values: {ss}"
    import httpx
    r = httpx.post("https://ai.dev.gientechai.com/v1/chat/completions",
        headers={"Authorization": "Bearer 123"},
        json={"model": "GS-Qwen3.6-35B-A3B",
              "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":user}],
              "temperature": 0, "max_tokens": 400}, timeout=120)
    content = r.json()["choices"][0]["message"]["content"]
    import re as _re
    mm = _re.search(r"\{.*\}", content, _re.S)
    payload = json.loads(mm.group(0) if mm else content)
    out[col] = {"samples": ss[:4], **payload}
    print(f"{col}: zh={payload['zh'][:60]}")
json.dump(out, open('/tmp/cube-live/gen_desc_schools.json','w'), ensure_ascii=False, indent=1)
print("saved ->", '/tmp/cube-live/gen_desc_schools.json')
