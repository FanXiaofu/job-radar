"""抽取准确率评测：对 golden_samples.jsonl 逐条跑抽取器，计算字段级准确率。

用法：python eval/run_eval.py
需要 .env 中配置 LLM_API_KEY。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.extractor import JobExtractor  # noqa: E402

FIELDS = ["company_name", "title", "recruit_type", "location", "apply_url"]


def load_samples() -> list[dict]:
    path = Path(__file__).parent / "golden_samples.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(value: str) -> str:
    return (value or "").strip().lower()


def main() -> None:
    samples = load_samples()
    if not samples:
        print("评测集为空，请在 eval/golden_samples.jsonl 中添加样本")
        return
    extractor = JobExtractor()
    field_hits = {f: 0 for f in FIELDS}
    full_hits = 0
    results = []
    for s in samples:
        pred = extractor.extract(s["raw"])
        if pred is None:
            results.append({"id": s["id"], "ok": False, "reason": "抽取失败"})
            continue
        ok_fields = {}
        for f in FIELDS:
            expect = normalize(s["expect"].get(f, ""))
            actual = normalize(str(pred.get(f, "")))[: len(expect) * 2] if expect else normalize(str(pred.get(f, "")))
            # apply_url 只比较是否包含预期路径（LLM 可能补全域名）
            hit = (expect in actual) if expect else (actual == "")
            ok_fields[f] = hit
            field_hits[f] += hit
        if all(ok_fields.values()):
            full_hits += 1
        results.append({"id": s["id"], "ok": all(ok_fields.values()),
                        "fields": ok_fields, "pred": pred})
    n = len(samples)
    print(f"样本数: {n}")
    print(f"整条准确率: {full_hits}/{n} = {full_hits / n:.1%}")
    for f in FIELDS:
        print(f"  {f}: {field_hits[f]}/{n} = {field_hits[f] / n:.1%}")
    out = Path(__file__).parent / "last_eval_result.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"明细已写入 {out}")


if __name__ == "__main__":
    main()
