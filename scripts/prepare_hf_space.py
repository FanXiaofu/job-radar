"""准备 Hugging Face Docker Space 的最小部署目录。

只复制运行所需文件，并把 deploy/hf-space/README.md 作为 Space 的 README。
用法：
    python scripts/prepare_hf_space.py --out _hf_space
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["config.py", "main.py", "pipeline.py", "requirements.lock", "Dockerfile", ".dockerignore"]
DIRS = ["app", "agent", "crawler", "db", "seed"]


def main() -> None:
    parser = argparse.ArgumentParser(description="准备 HF Docker Space 目录")
    parser.add_argument("--out", default="_hf_space", help="输出目录")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的输出目录")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        if not args.force:
            raise SystemExit(f"目录已存在，加 --force 覆盖: {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for name in FILES:
        src = ROOT / name
        if not src.exists():
            raise SystemExit(f"缺少文件: {src}")
        shutil.copy2(src, out / name)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in DIRS:
        shutil.copytree(ROOT / name, out / name, ignore=ignore)

    shutil.copy2(ROOT / "deploy/hf-space/README.md", out / "README.md")
    print(f"HF Space 目录已生成: {out}")
    print("下一步：克隆 HF Space 仓库，把本目录内容复制进去后 git add/commit/push")


if __name__ == "__main__":
    main()
