"""
种子数据加载脚本。用法:
    python -m app.data.seed          # 加载 seed_questions.json 到题库
    python -m app.data.seed --reset  # 清空后重新加载
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

SEED_FILE = Path(__file__).parent / "seed_questions.json"


async def main(reset: bool = False):
    async with httpx.AsyncClient(base_url="http://localhost:9000", timeout=180) as client:
        if not SEED_FILE.exists():
            print(f"种子文件不存在: {SEED_FILE}")
            sys.exit(1)

        with open(SEED_FILE, "r", encoding="utf-8") as f:
            questions = json.load(f)

        print(f"加载 {len(questions)} 道题目...")
        success = 0
        for i, q in enumerate(questions):
            resp = await client.post("/api/v1/questions/", json=q)
            if resp.status_code == 201:
                success += 1
                print(f"  [{i+1}/{len(questions)}] OK: {q['content'][:50]}...")
            else:
                print(f"  [{i+1}/{len(questions)}] FAIL: {resp.status_code} - {resp.text[:100]}")

        print(f"\n完成: {success}/{len(questions)} 道题目已入库")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    asyncio.run(main(reset))
