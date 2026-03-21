#!/usr/bin/env python3
"""文字統計腳本 — Example Skill

用法:
    python count.py "要統計的文字"
    python count.py  # 從 stdin 讀取
"""
import sys


def count_text(text: str) -> dict:
    no_ws = text.replace(" ", "").replace("\n", "").replace("\t", "")
    lines = text.splitlines()
    return {
        "字元數（含空白）": len(text),
        "字元數（不含空白）": len(no_ws),
        "英文單字數": len(text.split()),
        "行　　數": len(lines) if lines else 1,
    }


def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read()

    if not text:
        print("（空字串）")
        for key in ["字元數（含空白）", "字元數（不含空白）", "英文單字數", "行　　數"]:
            print(f"{key}: 0")
        sys.exit(0)

    stats = count_text(text)
    for key, val in stats.items():
        print(f"{key}: {val}")


if __name__ == "__main__":
    main()
