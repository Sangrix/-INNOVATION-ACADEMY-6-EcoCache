"""
EcoCache Eval Dashboard — Streamlit
실행: streamlit run eval_dashboard.py
"""

import json
import warnings
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

st.set_page_config(page_title="EcoCache Eval", page_icon="📊", layout="wide")

# ── 유틸 ──────────────────────────────────────────────────────────────────────

def load_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def status_icon(qa_score: float | None, threshold: float, margin: float) -> str:
    if qa_score is None:
        return "⚪"
    if qa_score >= threshold + margin:
        return "🟢"
    if qa_score >= threshold - margin:
        return "🟡"
    return "🔴"


def config_label(cfg: dict) -> str:
    model = cfg["embed_model"].split("/")[-1]
    return f"{model} | th={cfg['qa_similarity_threshold']} | chunk={cfg['chunk_size']}"


def entries_to_df(entries: list[dict], threshold: float, margin: float) -> pd.DataFrame:
    rows = []
    for i, e in enumerate(entries):
        r1 = e["results"][0] if e["results"] else {}
        qa = e.get("qa_top1_score")
        rows.append({
            "_idx":    i,
            "상태":    status_icon(qa, threshold, margin),
            "쿼리":    e["query"],
            "출처":    e["source"],
            "Top1":    round(r1.get("score", 0), 4),
            "QA Top1": round(qa, 4) if qa is not None else None,
            "Config":  config_label(e["config"]),
            "시각":    e["timestamp"][:19].replace("T", " "),
        })
    return pd.DataFrame(rows)


# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ 설정")
    log_path = st.text_input("로그 파일", value="eval_log.jsonl")
    threshold = st.slider("QA Threshold", 0.50, 1.00, 0.75, 0.01)
    margin    = st.slider("경계 마진 (±)", 0.01, 0.10, 0.05, 0.01)
    st.caption(
        f"🟢 ≥ {threshold+margin:.2f}  "
        f"🟡 {threshold-margin:.2f}~{threshold+margin:.2f}  "
        f"🔴 < {threshold-margin:.2f}"
    )
    st.divider()
    source_filter = st.multiselect("출처 필터", ["qa_pairs", "documents"],
                                   default=["qa_pairs", "documents"])
    model_kw = st.text_input("모델명 키워드 필터", value="")

# ── 로드 & 필터 ───────────────────────────────────────────────────────────────

all_entries = load_log(Path(log_path))
if not all_entries:
    st.error(f"로그를 찾을 수 없습니다: {log_path}"); st.stop()

entries = [e for e in all_entries if e["source"] in source_filter]
if model_kw:
    entries = [e for e in entries if model_kw in e["config"]["embed_model"]]

# ── 상단 요약 메트릭 ──────────────────────────────────────────────────────────

st.title("📊 EcoCache Eval Dashboard")

scores    = [e["results"][0]["score"] for e in entries if e["results"]]
qa_scores = [e["qa_top1_score"] for e in entries if e.get("qa_top1_score") is not None]
qa_hit    = sum(1 for e in entries if e["source"] == "qa_pairs")
border    = sum(1 for s in qa_scores if abs(s - threshold) < margin)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("총 쿼리",     len(entries))
c2.metric("qa_pairs 히트", qa_hit,
          f"{qa_hit/len(entries)*100:.0f}%" if entries else "-")
c3.metric("Top1 평균",   f"{sum(scores)/len(scores):.4f}" if scores else "-")
c4.metric("QA Top1 평균", f"{sum(qa_scores)/len(qa_scores):.4f}" if qa_scores else "-")
c5.metric("🟡 경계 케이스", border)

st.divider()

# ── 탭 ───────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 결과 테이블", "📈 Score 분포", "🎚️ Threshold 시뮬레이터", "⚖️ 실험 비교"]
)

# ── Tab 1: 결과 테이블 ────────────────────────────────────────────────────────

with tab1:
    df = entries_to_df(entries, threshold, margin)

    col_sort, col_asc = st.columns([3, 1])
    sort_by  = col_sort.selectbox("정렬", ["시각", "Top1", "QA Top1"], index=0)
    asc_flag = col_asc.checkbox("오름차순", value=False)

    sort_df = df.copy()
    sort_df["_s"] = pd.to_numeric(sort_df[sort_by], errors="coerce")
    sort_df = sort_df.sort_values("_s" if sort_by != "시각" else "시각",
                                  ascending=asc_flag).reset_index(drop=True)

    # ── 행별 expander 렌더링 ─────────────────────────────────────────────────
    for _, row in sort_df.iterrows():
        e       = entries[row["_idx"]]
        icon    = row["상태"]
        top1    = row["Top1"]
        qa_top1 = row["QA Top1"]
        source  = row["출처"]

        qa_top1_str = f"{qa_top1:.4f}" if qa_top1 is not None else "-"
        label = (
            f"{icon}  {e['query']}  "
            f"│ {source}  │ top1 {top1:.4f}  │ QA top1 {qa_top1_str}"
        )

        with st.expander(label, expanded=False):

            # ── 메타 정보 ─────────────────────────────────────────────────
            st.caption(
                f"모델: {e['config']['embed_model']}  |  "
                f"임계값: {e['config']['qa_similarity_threshold']}  |  "
                f"청크: {e['config']['chunk_size']}  |  "
                f"시각: {e['timestamp'][:19].replace('T', ' ')}"
            )

            # ── Rank 카드 ─────────────────────────────────────────────────
            for r in e["results"]:
                rank   = r["rank"]
                score  = r["score"]
                is_qa  = "question" in r
                is_top = rank == 1

                border_color = "#1E88E5" if is_top else "#9E9E9E"
                bg_color     = "#E3F2FD" if is_top else "#F5F5F5"

                id_str   = r.get("qa_id", "") if is_qa else \
                           f"{r.get('doc_id', '')} · chunk {r.get('chunk_index', 0)}"
                type_str = "qa_pairs" if is_qa else "documents"

                # 카드 헤더
                st.markdown(
                    f"""<div style="
                        border-left: 4px solid {border_color};
                        background: {bg_color};
                        padding: 6px 12px 4px 12px;
                        border-radius: 4px;
                        margin-top: 10px;
                        font-size: 0.85rem;
                    ">
                    <b>Rank {rank}</b> &nbsp;|&nbsp;
                    score: <b>{score:.4f}</b> &nbsp;|&nbsp;
                    {type_str}: <code>{id_str}</code>
                    </div>""",
                    unsafe_allow_html=True,
                )

                # 카드 본문
                if is_qa:
                    st.markdown("**❓ 질문**")
                    st.write(r.get("question", ""))
                    st.markdown("**💬 답변**")
                    st.info(r.get("answer", ""))
                    st.caption(f"qa_id: `{r.get('qa_id', '')}`")
                else:
                    st.markdown(f"**📄 {r.get('title', '')}**")
                    st.caption(
                        f"doc_id: `{r.get('doc_id', '')}`  |  "
                        f"날짜: {r.get('published_at', '')}  |  "
                        f"chunk: {r.get('chunk_index', 0)}"
                    )
                    st.write(r.get("text_preview", ""))

                if rank < len(e["results"]):
                    st.markdown(
                        "<hr style='margin:6px 0; opacity:0.2'>",
                        unsafe_allow_html=True,
                    )

# ── Tab 2: Score 분포 ─────────────────────────────────────────────────────────

with tab2:
    df2 = entries_to_df(entries, threshold, margin)
    df2["Top1"]    = pd.to_numeric(df2["Top1"],    errors="coerce")
    df2["QA Top1"] = pd.to_numeric(df2["QA Top1"], errors="coerce")

    # Top1 히스토그램
    hist = (
        alt.Chart(df2)
        .mark_bar(opacity=0.75)
        .encode(
            x=alt.X("Top1:Q", bin=alt.Bin(maxbins=20), title="Top1 유사도"),
            y=alt.Y("count():Q", title="쿼리 수"),
            color=alt.Color(
                "출처:N",
                scale=alt.Scale(domain=["qa_pairs", "documents"],
                                range=["#4CAF50", "#2196F3"]),
            ),
            tooltip=["출처:N", "count():Q"],
        )
        .properties(height=280, title="Top1 Score 분포 (출처별)")
    )
    th_line = (
        alt.Chart(pd.DataFrame({"v": [threshold]}))
        .mark_rule(color="red", strokeDash=[6, 3])
        .encode(x="v:Q")
    )
    st.altair_chart(hist + th_line, use_container_width=True)

    # QA Top1 vs Top1 scatter
    st.subheader("QA Top1 vs 최종 Top1")
    scatter_df = df2.dropna(subset=["QA Top1"])
    lo, hi = 0.35, 1.0

    scatter = (
        alt.Chart(scatter_df)
        .mark_circle(size=90, opacity=0.8)
        .encode(
            x=alt.X("QA Top1:Q", scale=alt.Scale(domain=[lo, hi]), title="QA Top1 유사도"),
            y=alt.Y("Top1:Q",    scale=alt.Scale(domain=[lo, hi]), title="최종 Top1 유사도"),
            color=alt.Color(
                "출처:N",
                scale=alt.Scale(domain=["qa_pairs", "documents"],
                                range=["#4CAF50", "#2196F3"]),
            ),
            tooltip=["쿼리:N", "출처:N", "QA Top1:Q", "Top1:Q"],
        )
        .properties(height=380, title="대각선 아래 = fallback 후 score 손해 발생")
    )
    diag   = (
        alt.Chart(pd.DataFrame({"x": [lo, hi], "y": [lo, hi]}))
        .mark_line(color="gray", strokeDash=[4, 4], opacity=0.5)
        .encode(x="x:Q", y="y:Q")
    )
    v_line = (
        alt.Chart(pd.DataFrame({"v": [threshold]}))
        .mark_rule(color="red", strokeDash=[6, 3])
        .encode(x="v:Q")
    )
    st.altair_chart(scatter + diag + v_line, use_container_width=True)
    st.caption("빨간 세로선 = 현재 threshold. 선 왼쪽의 🟢 점 = threshold를 낮추면 qa_pairs로 전환")

# ── Tab 3: Threshold 시뮬레이터 ───────────────────────────────────────────────

with tab3:
    st.subheader("🎚️ Threshold 시뮬레이터")
    st.caption("슬라이더를 움직이면 qa_pairs / documents 분포가 실시간으로 바뀝니다.")

    sim_th = st.slider("시뮬레이션 Threshold", 0.50, 1.00, threshold, 0.01, key="sim")

    if qa_scores:
        sim_qa  = sum(1 for s in qa_scores if s >= sim_th)
        sim_doc = len(qa_scores) - sim_qa
        diff    = sim_qa - qa_hit

        c1, c2, c3 = st.columns(3)
        c1.metric("qa_pairs 응답", sim_qa,  f"{sim_qa/len(qa_scores)*100:.1f}%")
        c2.metric("documents fallback", sim_doc, f"{sim_doc/len(qa_scores)*100:.1f}%")
        c3.metric("현재 대비 변화", diff,
                  "개 더 qa_pairs" if diff > 0 else ("개 더 documents" if diff < 0 else "변화 없음"))

        # threshold 곡선
        th_range = [round(0.50 + i * 0.01, 2) for i in range(51)]
        curve_df = pd.DataFrame({
            "threshold":     th_range,
            "qa_pairs 비율": [
                sum(1 for s in qa_scores if s >= t) / len(qa_scores) * 100
                for t in th_range
            ],
        })
        curve = (
            alt.Chart(curve_df)
            .mark_line(color="#4CAF50", strokeWidth=2)
            .encode(
                x=alt.X("threshold:Q", title="Threshold"),
                y=alt.Y("qa_pairs 비율:Q", title="qa_pairs 응답 비율 (%)",
                        scale=alt.Scale(domain=[0, 100])),
            )
        )
        sim_vline = (
            alt.Chart(pd.DataFrame({"v": [sim_th]}))
            .mark_rule(color="red", strokeDash=[6, 3])
            .encode(x="v:Q")
        )
        orig_vline = (
            alt.Chart(pd.DataFrame({"v": [threshold]}))
            .mark_rule(color="orange", strokeDash=[3, 3])
            .encode(x="v:Q")
        )
        st.altair_chart(curve + sim_vline + orig_vline, use_container_width=True)
        st.caption("빨간선 = 시뮬레이션 threshold  |  주황선 = 사이드바 threshold")

        # 전환 케이스 목록
        if sim_th != threshold:
            converted = []
            for e in entries:
                qa_s = e.get("qa_top1_score")
                if qa_s is None:
                    continue
                was_qa = qa_s >= threshold
                now_qa = qa_s >= sim_th
                if was_qa != now_qa:
                    converted.append({
                        "쿼리":    e["query"],
                        "QA Top1": round(qa_s, 4),
                        "변화":    "📥 documents → qa_pairs" if now_qa
                                   else "📤 qa_pairs → documents",
                    })
            if converted:
                st.write(f"**threshold {threshold:.2f} → {sim_th:.2f} 변경 시 전환 ({len(converted)}건)**")
                st.dataframe(pd.DataFrame(converted), use_container_width=True, hide_index=True)
            else:
                st.info("전환되는 케이스가 없습니다.")
    else:
        st.info("qa_top1_score 데이터가 없습니다.")

# ── Tab 4: 실험 비교 ──────────────────────────────────────────────────────────

with tab4:
    st.subheader("⚖️ Config별 실험 비교")

    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(config_label(e["config"]), []).append(e)

    if len(groups) == 1:
        st.info(
            "현재 로그에 실험 그룹이 1개입니다.\n\n"
            "다른 config(모델·threshold·chunk_size)로 `python run_eval.py --log-file other.jsonl`을 실행한 뒤 "
            "두 파일을 합쳐서 로드하면 여기서 비교됩니다."
        )

    # 요약 테이블
    summary = []
    for key, grp in groups.items():
        s  = [e["results"][0]["score"] for e in grp if e["results"]]
        qs = [e["qa_top1_score"] for e in grp if e.get("qa_top1_score") is not None]
        qh = sum(1 for e in grp if e["source"] == "qa_pairs")
        summary.append({
            "Config":       key,
            "쿼리 수":      len(grp),
            "qa_pairs":     qh,
            "qa 비율":      f"{qh/len(grp)*100:.1f}%",
            "Top1 평균":    f"{sum(s)/len(s):.4f}"  if s  else "-",
            "QA Top1 평균": f"{sum(qs)/len(qs):.4f}" if qs else "-",
        })
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

    if len(groups) > 1:
        # 박스플롯 비교
        box_rows = []
        for key, grp in groups.items():
            for e in grp:
                if e["results"]:
                    box_rows.append({"Config": key, "Top1": e["results"][0]["score"]})
        box_df = pd.DataFrame(box_rows)

        box = (
            alt.Chart(box_df)
            .mark_boxplot(extent="min-max")
            .encode(
                x=alt.X("Config:N", title="실험 Config"),
                y=alt.Y("Top1:Q",   title="Top1 유사도",
                        scale=alt.Scale(domain=[0.3, 1.0])),
                color="Config:N",
            )
            .properties(height=380, title="Config별 Top1 Score 분포")
        )
        st.altair_chart(box, use_container_width=True)

        # 쿼리별 차이 히트맵 (같은 쿼리 비교)
        pivot_rows = []
        for key, grp in groups.items():
            for e in grp:
                pivot_rows.append({
                    "Config": key,
                    "쿼리":   e["query"][:30] + ("…" if len(e["query"]) > 30 else ""),
                    "Top1":   e["results"][0]["score"] if e["results"] else 0,
                })
        pivot_df = pd.DataFrame(pivot_rows)
        if not pivot_df.empty:
            heat = (
                alt.Chart(pivot_df)
                .mark_rect()
                .encode(
                    x=alt.X("Config:N"),
                    y=alt.Y("쿼리:N",   sort=None),
                    color=alt.Color("Top1:Q",
                                    scale=alt.Scale(scheme="blues", domain=[0.4, 1.0])),
                    tooltip=["쿼리:N", "Config:N", "Top1:Q"],
                )
                .properties(title="쿼리×Config Top1 히트맵")
            )
            st.altair_chart(heat, use_container_width=True)
