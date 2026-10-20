"""Small Streamlit components and the dashboard design system."""

from __future__ import annotations

import html

RED = "#E60012"
CHARCOAL = "#232326"

CSS = """
<style>
  .stApp { background: #FAFAF7; color: #232326; }
  section[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E8E8E6; }
  h1, h2, h3 { color: #232326; letter-spacing: -0.02em; }
  .nih-kicker { color:#E60012; font-size:0.78rem; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; }
  .nih-subtitle { color:#5B6470; font-size:1rem; margin-top:-0.4rem; }
  .nih-card { background:#FFFFFF; border:1px solid #E8E8E6; border-top:3px solid #E60012;
              border-radius:10px; padding:1rem 1.1rem; min-height:7.2rem; overflow:hidden; }
  .nih-card .label { color:#5B6470; font-size:0.78rem; font-weight:700; letter-spacing:0.08em;
                     text-transform:uppercase; overflow-wrap:break-word; }
  .nih-card .value { color:#232326; font-weight:750; line-height:1.15; margin-top:0.35rem;
                     font-size:clamp(1.2rem, 1.1rem + 0.9vw, 1.65rem);
                     white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .nih-card .note { color:#5B6470; font-size:0.82rem; margin-top:0.3rem; overflow-wrap:break-word; }
  .nih-status { display:inline-block; border-radius:999px; padding:0.18rem 0.65rem; font-size:0.8rem; font-weight:700; }
  .nih-ok { background:#E7F5EA; color:#176B2D; }
  .nih-bad { background:#FDE8E9; color:#9B111C; }
  .nih-warn { background:#FFF4D6; color:#7A5C00; }
  .nih-note { background:#FFFFFF; border:1px solid #E8E8E6; border-radius:10px; padding:0.9rem 1rem; }
  div[data-testid="stMetric"] { background:#FFFFFF; border:1px solid #E8E8E6; border-radius:10px; padding:0.7rem; }
</style>
"""


def apply_style(st) -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header(st, kicker: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="nih-kicker">{html.escape(kicker)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="nih-subtitle">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def disclaimer(st) -> None:
    st.caption(
        "Independent portfolio project. Not affiliated with, endorsed by, or sponsored by Nintendo. "
        "Figures are read from public Nintendo IR disclosures stored in the local warehouse."
    )


def kpi_card(st, label: str, value: str, note: str = "") -> None:
    st.markdown(
        '<div class="nih-card">'
        f'<div class="label">{html.escape(label)}</div>'
        f'<div class="value" title="{html.escape(value, quote=True)}">{html.escape(value)}</div>'
        f'<div class="note" title="{html.escape(note, quote=True)}">{html.escape(note)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def kpi_grid(st, items: list[tuple[str, str, str]], per_row: int = 2) -> None:
    """Render KPI cards in rows of at most `per_row` columns.

    Four-across rows made cards too narrow for timestamps and long
    values at laptop and tablet widths; two-across keeps labels and
    numbers on one line. Items are (label, value, note) tuples.
    """
    for start in range(0, len(items), per_row):
        row = items[start:start + per_row]
        columns = st.columns(len(row))
        for column, (label, value, note) in zip(columns, row, strict=True):
            with column:
                kpi_card(st, label, value, note)


def status_pill(status: str) -> str:
    normalized = str(status).lower()
    klass = "nih-ok" if normalized == "succeeded" else "nih-bad" if normalized == "failed" else "nih-warn"
    return f'<span class="nih-status {klass}">{html.escape(str(status))}</span>'


def insight_list(st, insights: list[str]) -> None:
    if not insights:
        st.info("No comparable observation is available for this selection.")
        return
    for insight in insights:
        st.markdown(f'<div class="nih-note">{html.escape(insight)}</div>', unsafe_allow_html=True)
