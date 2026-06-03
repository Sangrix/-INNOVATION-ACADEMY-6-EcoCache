#!/usr/bin/env python3.10
"""
EcoCache /chat API test report generator.

Usage:
    python3.10 tests/generate_report.py [--api-url http://localhost:8000]

Assumes the /chat API is already running.
Output: docs/reports/YYYY-MM-DD-chat-api-test-report.md
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

QA_FILES = [
    (DATA_DIR / "sw_upstage_output"   / "inha_notice_qa.json",                    "sw_upstage_output (공지사항 2026)"),
    (DATA_DIR / "sw_upstage_output_2" / "inha_sw_notice_qa_157275_to_166292.json", "sw_upstage_output_2 (공지사항 2025-11)"),
    (DATA_DIR / "sw_upstage_output_3" / "swuniv_notice_qa3.json",                  "sw_upstage_output_3 (공지사항 2025-12~2026)"),
    (DATA_DIR / "pr_data"             / "inha_pr_qa.json",                         "pr_data (외부홍보)"),
]

NOVEL_QUESTIONS = [
    "SW중심대학 사업단 소개 및 주요 목표는 무엇인가요?",
    "2026년 상반기에 진행되는 SW 관련 공모전 목록은?",
    "인하대 SW 전공 학생이 받을 수 있는 장학금 종류는 무엇인가요?",
    "SW중심대학 산학협력 프로그램에 참여하려면 어떻게 해야 하나요?",
    "오픈소스 프로젝트 참여 기회는 어떻게 찾을 수 있나요?",
    "인하대학교 SW중심대학 취업 연계 프로그램이 있나요?",
    "AI 관련 자격증 취득을 지원하는 프로그램에 대해 알려주세요.",
    "해외 인턴십이나 글로벌 프로그램을 지원하려면 무엇이 필요한가요?",
    "SW중심대학사업단이 주관하는 세미나나 특강 일정은 어디서 확인하나요?",
    "2025년 하반기 또는 2026년에 개최된 해커톤 정보가 있나요?",
]


def load_qa_batches(n_per_batch: int = 5) -> list[dict]:
    """Load n_per_batch QA pairs from each of the 4 data files."""
    results = []
    for qa_path, batch_name in QA_FILES:
        raw = json.loads(Path(qa_path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("qa_pairs", [])
        for item in items[:n_per_batch]:
            results.append({
                "query":           item["question"]["text"],
                "expected_answer": item["answer"]["text"],
                "batch":           batch_name,
                "type":            "qa_pair",
            })
    return results
