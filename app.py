"""UFC AI Predictor — Streamlit UI."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.config import DEFAULT_DB_PATH, all_math_stat_keys
from src.db.connection import get_connection, init_db
from src.db.repository import Repository
from src.engine.betting import BetAnalysis, analyze_bet, format_american
from src.engine.research import BlendedPrediction
from src.services.card_loader import (
    FightAnalysis,
    get_fight_market_lines,
    load_card_predictions,
    load_merged_odds,
)
from src.services.compare import compare_fighters
from src.services.ledger import (
    get_graded_predictions,
    get_lifetime_record,
    grade_pending,
    log_card_picks,
)
from src.services.weight_class import normalize_weight_class

st.set_page_config(
    page_title="UFC AI Predictor",
    page_icon="🥊",
    layout="wide",
    initial_sidebar_state="expanded",
)

TIER_COLORS = {
    "LOCK": "#22c55e",
    "STRONG": "#3b82f6",
    "LEAN": "#eab308",
    "COIN_FLIP": "#94a3b8",
    "NO_PICK": "#64748b",
}

VERDICT_COLORS = {
    "VALUE_DOG": "#22c55e",
    "VALUE_FAV": "#3b82f6",
    "PASS": "#64748b",
    "NO_LINE": "#94a3b8",
}


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False}

CATEGORY_DISPLAY = {
    "striking": "Striking",
    "grappling": "Grappling",
    "recent_form": "Recent Form",
    "style_matchup": "Style Matchup",
    "physical_edge": "Physical",
    "cardio": "Cardio",
    "durability": "Durability",
    "fight_iq": "Fight IQ",
    "judge_fit": "Judges",
    "context_math": "Context",
}

EVEN_THRESHOLD = 0.5
TEAL = "#2dd4bf"
ORANGE = "#fb923c"
MUTED = "#94a3b8"
BAR_GRAY = "#3d4f63"
BAR_TRACK = "#1a2332"


def _last_name(full: str) -> str:
    parts = full.strip().split()
    return parts[-1] if parts else full


def _sort_categories_shmoo(categories: list) -> list:
    """Red edges first (biggest gap), EVEN in the middle, blue edges last."""
    red_fav = [c for c in categories if c.gap > EVEN_THRESHOLD]
    even = [c for c in categories if abs(c.gap) <= EVEN_THRESHOLD]
    blue_fav = [c for c in categories if c.gap < -EVEN_THRESHOLD]
    red_fav.sort(key=lambda c: c.gap, reverse=True)
    even.sort(key=lambda c: abs(c.gap))
    blue_fav.sort(key=lambda c: abs(c.gap))
    return red_fav + even + blue_fav


def _category_breakdown_html(analysis: FightAnalysis) -> str:
    pred = analysis.blended.math
    red_name = analysis.red_name
    blue_name = analysis.blue_name
    red_short = _last_name(red_name)
    blue_short = _last_name(blue_name)
    sorted_cats = _sort_categories_shmoo(pred.categories)

    blocks: list[str] = []
    for i, cat in enumerate(sorted_cats):
        label = CATEGORY_DISPLAY.get(cat.name, cat.name.replace("_", " ").title())
        gap = cat.gap
        abs_gap = abs(gap)

        if abs_gap <= EVEN_THRESHOLD:
            edge_html = f'<span class="cat-edge cat-edge-even">EVEN</span>'
        elif gap > 0:
            edge_html = f'<span class="cat-edge cat-edge-red">{red_name} +{gap:.1f}</span>'
        else:
            edge_html = f'<span class="cat-edge cat-edge-blue">{blue_name} +{abs_gap:.1f}</span>'

        dot = '<span class="cat-dot"></span>' if i == 0 and abs_gap > EVEN_THRESHOLD else ""
        row_max = max(cat.red_score, cat.blue_score, 0.01)

        def fighter_row(fighter_short: str, score: float, is_teal: bool) -> str:
            pct = min(100.0, (score / row_max) * 100.0)
            bar_cls = "bar-teal" if is_teal else "bar-gray"
            return f"""
            <div class="fighter-row">
                <div class="fighter-label">{fighter_short}</div>
                <div class="bar-line">
                    <div class="bar-track">
                        <div class="bar {bar_cls}" style="width:{pct:.1f}%"></div>
                    </div>
                    <span class="bar-value">{score:.1f}</span>
                </div>
            </div>"""

        red_teal = cat.red_score >= cat.blue_score
        blocks.append(
            f"""
            <div class="cat-block">
                <div class="cat-header">
                    <span class="cat-name">{label}{dot}</span>
                    {edge_html}
                </div>
                {fighter_row(red_short, cat.red_score, red_teal)}
                {fighter_row(blue_short, cat.blue_score, not red_teal)}
            </div>"""
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    * {{ box-sizing: border-box; }}
    body {{
        margin: 0;
        padding: 0;
        background: transparent;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .shmoo-categories {{
        background: #0f172a;
        border-radius: 10px;
        padding: 0.75rem 1rem 1rem;
    }}
    .shmoo-categories .cat-block {{
        padding: 0.85rem 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }}
    .shmoo-categories .cat-block:last-child {{
        border-bottom: none;
        padding-bottom: 0;
    }}
    .shmoo-categories .cat-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.55rem;
        gap: 0.75rem;
    }}
    .shmoo-categories .cat-name {{
        font-weight: 700;
        font-size: 0.95rem;
        color: #f8fafc;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}
    .shmoo-categories .cat-dot {{
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: {TEAL};
        flex-shrink: 0;
    }}
    .shmoo-categories .cat-edge {{
        font-size: 0.8rem;
        font-weight: 600;
        white-space: nowrap;
    }}
    .shmoo-categories .cat-edge-red {{ color: {TEAL}; }}
    .shmoo-categories .cat-edge-blue {{ color: {ORANGE}; }}
    .shmoo-categories .cat-edge-even {{ color: {MUTED}; font-weight: 500; }}
    .shmoo-categories .fighter-row {{
        margin-bottom: 0.35rem;
    }}
    .shmoo-categories .fighter-row:last-child {{
        margin-bottom: 0;
    }}
    .shmoo-categories .fighter-label {{
        font-size: 0.72rem;
        color: {MUTED};
        margin-bottom: 0.2rem;
    }}
    .shmoo-categories .bar-line {{
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }}
    .shmoo-categories .bar-track {{
        flex: 1;
        height: 8px;
        background: {BAR_TRACK};
        border-radius: 999px;
        overflow: hidden;
    }}
    .shmoo-categories .bar {{
        height: 100%;
        border-radius: 999px;
        min-width: 2px;
    }}
    .shmoo-categories .bar-teal {{ background: {TEAL}; }}
    .shmoo-categories .bar-gray {{ background: {BAR_GRAY}; }}
    .shmoo-categories .bar-value {{
        font-size: 0.8rem;
        color: {MUTED};
        min-width: 2.2rem;
        text-align: right;
    }}
</style>
</head>
<body>
    <div class="shmoo-categories">
        {"".join(blocks)}
    </div>
    <script>
    (function () {{
        function sendHeight() {{
            const h = Math.ceil(document.documentElement.scrollHeight);
            window.parent.postMessage({{ type: "streamlit:setFrameHeight", height: h }}, "*");
        }}
        sendHeight();
        window.addEventListener("load", sendHeight);
        new ResizeObserver(sendHeight).observe(document.body);
    }})();
    </script>
</body>
</html>"""


def _render_category_breakdown(analysis: FightAnalysis) -> None:
    n_cats = len(analysis.blended.math.categories)
    height = 100 + n_cats * 115
    components.html(_category_breakdown_html(analysis), height=height, scrolling=True)


def _edge_chart(blended: BlendedPrediction, bet: BetAnalysis) -> go.Figure | None:
    if bet.vegas_implied is None:
        return None
    labels = ["AI model"]
    values = [blended.win_prob * 100]
    colors = ["#8b5cf6"]
    source = bet.market_source or "Market"
    labels.append(source)
    values.append(bet.vegas_implied * 100)
    colors.append("#f59e0b")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[_pct(blended.win_prob), _pct(bet.vegas_implied)],
            textposition="outside",
        )
    )
    ymax = max(values) + 12
    fig.update_layout(
        title="The Edge · AI vs market",
        height=300,
        yaxis=dict(title="Win probability (%)", range=[0, ymax]),
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.5)",
    )
    return fig


def _load_card_data(db_path: str, event_filter: str, *, force_refresh: bool = False) -> dict:
    cache_key = f"card_{db_path}_{event_filter}"
    if force_refresh and cache_key in st.session_state:
        del st.session_state[cache_key]
    if cache_key not in st.session_state:
        card = load_card_predictions(
            Path(db_path),
            event_name=event_filter or None,
            use_polymarket=True,
        )
        st.session_state[cache_key] = {"event": card.event, "analyses": card.analyses}
    return st.session_state[cache_key]


def _render_bet_box(bet: BetAnalysis, bankroll: float) -> None:
    color = VERDICT_COLORS.get(bet.verdict, "#94a3b8")
    st.markdown(
        f"""
        <div style="border-left: 4px solid {color}; padding: 1rem 1.25rem;
                    background: #1e293b; border-radius: 8px; margin: 1rem 0;">
            <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;
                        letter-spacing: 0.05em;">Bet Verdict · {bet.market_source or 'Market'}</div>
            <div style="font-size: 1.25rem; font-weight: 700; color: {color}; margin: 0.25rem 0;">
                {bet.verdict.replace("_", " ")}
            </div>
            <div style="color: #e2e8f0;">{bet.detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if bet.edge is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Edge", f"{bet.edge_points:+.1f} pts")
        c2.metric("EV / $1", f"${bet.ev_per_unit:+.2f}" if bet.ev_per_unit is not None else "—")
        c3.metric("Half-Kelly", _pct(bet.half_kelly_fraction or 0))
        c4.metric(f"Stake (${bankroll:.0f} bank)", f"${bet.half_kelly_stake or 0:.2f}")


def _render_research_box(blended: BlendedPrediction) -> None:
    research = blended.research
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
            <div style="padding: 1rem; background: #1e293b; border-radius: 8px; min-height: 180px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;
                            letter-spacing: 0.05em;">Why This Pick</div>
                <div style="color: #94a3b8; font-size: 0.8rem;">Math + Research</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if research.why_pick:
            for bullet in research.why_pick:
                st.markdown(f"- {bullet}")
        else:
            st.caption("No strong supporting signals.")

    with col2:
        st.markdown(
            """
            <div style="padding: 1rem; background: #1e293b; border-radius: 8px; min-height: 180px;">
                <div style="font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;
                            letter-spacing: 0.05em;">Watch Out</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if research.watch_out:
            for bullet in research.watch_out:
                st.markdown(f"- {bullet}")
        else:
            st.caption("No major red flags.")

    if research.red_adjustment or research.blue_adjustment:
        st.caption(
            f"Research adjustment (capped): {blended.math.red_name} {research.red_adjustment:+.1%}, "
            f"{blended.math.blue_name} {research.blue_adjustment:+.1%} · "
            f"Math pick {_pct(blended.math_win_prob)} → Final {_pct(blended.win_prob)}"
        )


def _build_bet(analysis: FightAnalysis, blended: BlendedPrediction, bankroll: float, yaml_odds: dict) -> BetAnalysis:
    red_ml, blue_ml, red_imp, blue_imp, source = get_fight_market_lines(analysis, yaml_odds)
    pick_imp = red_imp if blended.pick_corner == "red" else blue_imp
    return analyze_bet(
        blended.pick_corner,
        blended.pick_name,
        blended.win_prob,
        blended.tier,
        red_ml,
        blue_ml,
        bankroll=bankroll,
        market_implied=pick_imp,
        market_source=source if pick_imp is not None else "Polymarket",
    )


def _render_fight(
    analysis: FightAnalysis,
    bankroll: float,
    yaml_odds: dict,
    *,
    sandbox: bool = False,
    pool_label: str | None = None,
    stat_caption: str | None = None,
) -> None:
    blended = analysis.blended
    tier_color = TIER_COLORS.get(blended.tier, "#94a3b8")
    bet = _build_bet(analysis, blended, bankroll, yaml_odds) if not sandbox else None
    pick_ml = bet.pick_ml if bet else None
    ml_label = format_american(pick_ml) if pick_ml is not None else "—"

    if sandbox:
        st.markdown(
            """
            <div style="padding:0.65rem 1rem;background:#164e63;border-radius:8px;
                        border-left:4px solid #22d3ee;margin-bottom:0.75rem;">
                <span style="color:#a5f3fc;font-weight:600;">Sandbox</span>
                <span style="color:#94a3b8;"> · hypothetical matchup · not logged to ledger</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if pool_label:
            st.caption(f"Normalization: {pool_label}")
        if stat_caption:
            st.caption(stat_caption)

    st.markdown(f"### {analysis.red_name} vs {analysis.blue_name}")
    st.caption(analysis.weight_class or "Weight class TBD")

    if analysis.polymarket and not sandbox:
        st.caption(
            f"Polymarket: {_pct(analysis.polymarket.red_prob)} {analysis.red_name} · "
            f"{_pct(analysis.polymarket.blue_prob)} {analysis.blue_name}"
        )

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.markdown(
            f"""
            <div style="padding: 1rem; background: #1e293b; border-radius: 8px;">
                <span style="color: {tier_color}; font-weight: 700;">{blended.tier}</span>
                <span style="color: #94a3b8;"> · Math + Research</span>
                <h2 style="margin: 0.5rem 0 0; color: #f8fafc;">
                    {blended.pick_name}
                    <span style="font-size: 1rem; color: #94a3b8;">ML {ml_label}</span>
                </h2>
                <p style="margin: 0.25rem 0; font-size: 1.5rem; color: #e2e8f0;">
                    {_pct(blended.win_prob)}
                    <span style="font-size: 0.9rem; color: #94a3b8;">
                        range {_pct(blended.prob_low)} - {_pct(blended.prob_high)}
                    </span>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.metric(analysis.red_name, _pct(blended.red_win_prob))
    with c3:
        st.metric(analysis.blue_name, _pct(blended.blue_win_prob))

    _render_research_box(blended)
    if bet and not sandbox:
        _render_bet_box(bet, bankroll)

    left, right = st.columns([1.4, 1])
    with left:
        _render_category_breakdown(analysis)
    with right:
        if sandbox:
            st.info("No market line in sandbox mode.")
        elif bet:
            edge_fig = _edge_chart(blended, bet)
            if edge_fig:
                st.plotly_chart(edge_fig, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("Polymarket line not found for this fight.")


def _render_live_record(db_path: str) -> None:
    init_db(Path(db_path))
    record = get_lifetime_record(Path(db_path))

    st.markdown("#### Live Record · Moneyline picks")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wins", record.wins)
    c2.metric("Losses", record.losses)
    c3.metric(
        "Hit Rate",
        f"{record.hit_rate * 100:.1f}%" if record.hit_rate is not None else "—",
    )
    c4.metric("Units", f"{record.units:+.2f}u")

    if record.pending:
        st.caption(f"{record.pending} pick(s) pending grading after the card.")

    with st.expander("Show previous card results", expanded=False):
        graded = get_graded_predictions(Path(db_path), limit=30)
        if not graded:
            st.caption("No graded picks yet. Lock picks before the card, then grade after results.")
        else:
            rows = []
            for row in graded:
                rows.append({
                    "Result": row["status"].upper(),
                    "Event": row.get("event_name"),
                    "Fight": f"{row['red_name']} vs {row['blue_name']}",
                    "Pick": row["pick_name"],
                    "Tier": row["tier"],
                    "Units": f"{(row.get('units') or 0):+.2f}",
                    "Winner": row.get("winner_name"),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)


MATH_STAT_COUNT = len(all_math_stat_keys())


def _fighter_display_label(fighter: dict) -> str:
    stats = fighter.get("stats") or {}
    w, l, d = stats.get("wins"), stats.get("losses"), stats.get("draws")
    if w is not None:
        return f"{fighter['name']} ({int(w)}-{int(l or 0)}-{int(d or 0)})"
    return fighter["name"]


def _load_fighter_roster(db_path: str, *, force_refresh: bool = False) -> list[dict]:
    cache_key = f"fighter_roster_{db_path}"
    if force_refresh and cache_key in st.session_state:
        del st.session_state[cache_key]
    if cache_key not in st.session_state:
        init_db(Path(db_path))
        with get_connection(Path(db_path)) as conn:
            st.session_state[cache_key] = Repository(conn).list_fighters_with_stats()
    return st.session_state[cache_key]


def _stat_completeness(name: str, missing: list[str]) -> str:
    have = MATH_STAT_COUNT - len(missing)
    return f"{name}: {have}/{MATH_STAT_COUNT} stats"


def _render_compare_sandbox(db_path: str, bankroll: float) -> None:
    st.markdown("#### Compare sandbox")
    st.caption("Pick any two fighters in your database — same math + research, no ledger, no market lines.")

    fighters = _load_fighter_roster(db_path)
    if not fighters:
        st.warning("No fighters with stats. Run `python -m src.ingest --last-cards` and `--upcoming` first.")
        return

    st.caption(f"{len(fighters)} fighters in roster")

    labels = {f["fighter_id"]: _fighter_display_label(f) for f in fighters}
    ids = [f["fighter_id"] for f in fighters]

    init_db(Path(db_path))
    with get_connection(Path(db_path)) as conn:
        wc_map = Repository(conn).get_latest_weight_classes()
    wc_options = sorted(
        {normalize_weight_class(wc) for wc in wc_map.values() if normalize_weight_class(wc)}
    )

    col_a, col_b = st.columns(2)
    with col_a:
        search_a = st.text_input("Search fighter A", placeholder="Type to filter…", key="cmp_search_a")
        red_pool = [i for i in ids if search_a.lower() in labels[i].lower()] if search_a else ids
        if not red_pool:
            red_pool = ids[:1]
        red_id = st.selectbox(
            "Fighter A · red corner", red_pool, format_func=lambda i: labels[i], key="cmp_red"
        )
    with col_b:
        search_b = st.text_input("Search fighter B", placeholder="Type to filter…", key="cmp_search_b")
        blue_pool = [i for i in ids if search_b.lower() in labels[i].lower()] if search_b else ids
        if not blue_pool:
            blue_pool = ids[:1]
        blue_id = st.selectbox(
            "Fighter B · blue corner", blue_pool, format_func=lambda i: labels[i], key="cmp_blue"
        )

    with st.expander("Sandbox options", expanded=False):
        pool_mode = st.radio(
            "Percentile pool",
            options=["weight_class", "full_roster"],
            format_func=lambda x: "Weight class division" if x == "weight_class" else "Full roster",
            horizontal=True,
        )
        wc_choice = st.selectbox(
            "Weight class override",
            options=["Auto"] + wc_options,
            help="Auto uses each fighter's most recent UFC bout division.",
        )
        scheduled_rounds = st.selectbox("Scheduled rounds", options=[3, 5], index=0)
        title_fight = st.checkbox("Title fight (5 rounds, cardio + research context)")

    if st.button("Run comparison", type="primary", key="cmp_run"):
        if red_id == blue_id:
            st.error("Pick two different fighters.")
        else:
            try:
                wc_override = None if wc_choice == "Auto" else wc_choice
                result = compare_fighters(
                    Path(db_path),
                    red_fighter_id=red_id,
                    blue_fighter_id=blue_id,
                    weight_class=wc_override,
                    pool_mode=pool_mode,
                    title_fight=title_fight,
                    scheduled_rounds=scheduled_rounds,
                )
                st.session_state["compare_result"] = result
            except ValueError as exc:
                st.error(str(exc))

    result = st.session_state.get("compare_result")
    if result:
        stat_caption = (
            f"{_stat_completeness(result.analysis.red_name, result.red_missing)} · "
            f"{_stat_completeness(result.analysis.blue_name, result.blue_missing)}"
        )
        st.divider()
        _render_fight(
            result.analysis,
            bankroll,
            {},
            sandbox=True,
            pool_label=result.pool_label,
            stat_caption=stat_caption,
        )


def main() -> None:
    st.title("UFC AI Predictor")
    st.caption("47 stats · 10 categories · Polymarket lines · Honest ledger")

    with st.sidebar:
        st.header("Settings")
        db_path = st.text_input("Database", value=str(DEFAULT_DB_PATH))
        event_filter = st.text_input("Event name filter (optional)", value="")
        bankroll = st.number_input("Bankroll ($)", min_value=100.0, value=1000.0, step=100.0)
        st.divider()
        st.subheader("Ledger")
        st.caption(
            "Optional in the UI — same as `python -m src.grade --log` / `--grade`. "
            "If you already ran those commands, picks are locked; use Grade after the card."
        )
        if st.button("Lock picks for this card", type="primary"):
            result = log_card_picks(
                Path(db_path),
                event_name=event_filter or None,
                bankroll=bankroll,
            )
            st.success(f"Logged {result.logged} picks ({result.skipped} already locked).")
        if st.button("Grade pending picks"):
            n = grade_pending(Path(db_path), event_name=event_filter or None)
            st.success(f"Graded {n} pick(s).")
        st.divider()
        st.subheader("Odds")
        st.caption("Live moneylines from Polymarket Gamma API.")
        if st.button("Refresh Polymarket"):
            _load_card_data(db_path, event_filter, force_refresh=True)
            st.rerun()

    _render_live_record(db_path)

    try:
        card = _load_card_data(db_path, event_filter)
    except ValueError as exc:
        st.error(str(exc))
        st.info("Run `python -m src.ingest --upcoming` first.")
        return

    event = card["event"]
    analyses: list[FightAnalysis] = card["analyses"]
    yaml_odds = load_merged_odds()

    st.subheader(event["name"])
    st.write(event.get("event_date") or "Date TBD", "·", event.get("location") or "")

    poly_count = sum(1 for a in analyses if a.polymarket)
    st.caption(f"Polymarket lines matched: {poly_count}/{len(analyses)} fights")

    tab_card, tab_fight, tab_compare = st.tabs(["Card overview", "Fight analyzer", "Compare sandbox"])

    with tab_compare:
        _render_compare_sandbox(db_path, bankroll)

    with tab_card:
        rows = []
        for analysis in analyses:
            blended = analysis.blended
            bet = _build_bet(analysis, blended, bankroll, yaml_odds)
            rows.append({
                "Fight": f"{analysis.red_name} vs {analysis.blue_name}",
                "Pick": blended.pick_name,
                "Tier": blended.tier,
                "Win %": round(blended.win_prob * 100, 1),
                "Poly %": round(bet.vegas_implied * 100, 1) if bet.vegas_implied else None,
                "Edge": f"{bet.edge_points:+.1f}" if bet.edge_points is not None else "—",
                "Verdict": bet.verdict,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with tab_fight:
        labels = [f"{a.red_name} vs {a.blue_name}" for a in analyses]
        choice = st.selectbox("Select fight", labels, index=0)
        analysis = analyses[labels.index(choice)]
        _render_fight(analysis, bankroll, yaml_odds)


if __name__ == "__main__":
    main()
