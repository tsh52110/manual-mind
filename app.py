"""ManualMind — chat over public equipment service manuals with cited answers."""
import json
import os
from pathlib import Path

import streamlit as st

from src.config import CONFIGS, MANUALS

st.set_page_config(
    page_title="ManualMind — Service Manual Assistant",
    page_icon="🔧",
    layout="centered",
    initial_sidebar_state="expanded",
)

# HF Spaces / Streamlit Cloud: key arrives via st.secrets, not .env
if not os.environ.get("ANTHROPIC_API_KEY"):
    try:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        pass

# ---------------------------------------------------------------- design tokens
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --primary: #1E3A5F;      /* navy */
  --primary-soft: #E8EEF5;
  --accent: #047857;       /* emerald-700: white text passes AA (5.4:1) */
  --fg: #0F172A;
  --fg-muted: #475569;
  --bg: #F8FAFC;
  --surface: #FFFFFF;
  --border: #E4E7EB;
  --radius: 12px;
}
html, body,
[data-testid="stAppViewContainer"] *:not([data-testid="stIconMaterial"]):not([class*="material-symbols"]) {
  font-family: 'IBM Plex Sans', sans-serif;
}
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
code, .mono { font-family: 'JetBrains Mono', monospace; }

/* chat bubbles: user = navy fill, assistant = white card */
[data-testid="stChatMessage"] {
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: var(--primary);
  border-color: var(--primary);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) li,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) p,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) li {
  color: #FFFFFF;
}

/* source cards */
.src-grid { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 8px 0; }
.src-card {
  flex: 1 1 240px; max-width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: 8px;
  padding: 8px 12px;
  transition: box-shadow 200ms ease;
}
.src-card:hover { box-shadow: 0 2px 8px rgba(15, 23, 42, 0.10); }
.src-card .tm {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px; font-weight: 600;
  color: var(--primary);
  letter-spacing: 0.02em;
}
.src-card .title { font-size: 13px; color: var(--fg); line-height: 1.5; }
.src-card .snippet {
  font-size: 12px; color: var(--fg-muted); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-top: 4px;
}
.badge {
  display: inline-block; float: right;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
  color: #FFFFFF; background: var(--primary);
  border-radius: 6px; padding: 2px 8px;
}
.src-label {
  font-size: 12px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--fg-muted); margin: 8px 0 4px 0;
  display: flex; align-items: center; gap: 6px;
}

/* sidebar manual list */
.manual-item {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 8px 10px; margin-bottom: 6px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px;
}
.manual-item .m-title { font-size: 13px; font-weight: 500; color: var(--fg); line-height: 1.45; }
.manual-item .m-tm {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: var(--fg-muted);
}
.manual-item svg { flex-shrink: 0; margin-top: 2px; }

/* empty state */
.empty-wrap { text-align: center; padding: 40px 16px 24px 16px; }
.empty-wrap h3 { font-weight: 600; color: var(--fg); margin: 16px 0 8px 0; }
.empty-wrap p { color: var(--fg-muted); font-size: 15px; line-height: 1.6; max-width: 44ch; margin: 0 auto; }

/* hero header */
.hero { display: flex; align-items: center; gap: 12px; padding: 8px 0 0 0; }
.hero .word { font-size: 26px; font-weight: 700; color: var(--fg); letter-spacing: -0.01em; }
.hero .word span { color: var(--primary); }
.hero .sub { font-size: 14px; color: var(--fg-muted); }

/* buttons: visible focus, no layout shift */
button:focus-visible { outline: 3px solid #2563EB !important; outline-offset: 2px; }
[data-testid="stChatInput"] textarea { font-size: 16px; }

@media (prefers-reduced-motion: reduce) {
  * { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

ICON_BOOK = """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1E3A5F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="manual"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>"""
ICON_WRENCH = """<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#1E3A5F" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="ManualMind"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>"""
ICON_CITE = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>"""

SUGGESTIONS = [
    "How deep can the HMMWV ford water without a fording kit?",
    "What fuels can the MEP-802A generator run on?",
    "Which way should the forks point when driving a loaded forklift downhill?",
]


@st.cache_resource(show_spinner=False)
def warm(config_name: str) -> bool:
    """Load embeddings + index once per config so first question isn't cold."""
    from src.rag import _vectorstore
    _vectorstore(CONFIGS[config_name].index_name)
    return True


def render_sources(sources: list[dict]) -> None:
    cards = "".join(
        f'<div class="src-card">'
        f'<span class="badge">p.{s["page"]}</span>'
        f'<div class="tm">{s["tm"]}</div>'
        f'<div class="title">{s["manual"]}</div>'
        f'<div class="snippet">{s["snippet"]}</div>'
        f"</div>"
        for s in sources
    )
    st.markdown(
        f'<div class="src-label">{ICON_CITE} Cited sources</div>'
        f'<div class="src-grid">{cards}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(
        f'<div class="hero">{ICON_WRENCH}<div><div class="word">Manual<span>Mind</span></div>'
        '<div class="sub">Grounded answers from service manuals</div></div></div>',
        unsafe_allow_html=True,
    )
    st.divider()

    config_name = st.selectbox(
        "Retrieval configuration",
        options=list(CONFIGS),
        index=list(CONFIGS).index("reranker") if "reranker" in CONFIGS else 0,
        help="Each configuration was measured with Ragas — see the README comparison table.",
    )
    st.caption(CONFIGS[config_name].description)

    st.divider()
    st.markdown(f"**Indexed manuals** · {len(MANUALS)}")
    for tm, title in MANUALS.items():
        st.markdown(
            f'<div class="manual-item">{ICON_BOOK}<div>'
            f'<div class="m-title">{title}</div>'
            f'<div class="m-tm">{tm}</div></div></div>',
            unsafe_allow_html=True,
        )

    results_dir = Path(__file__).parent / "evals" / "results"
    summary = results_dir / f"{config_name}_summary.json"
    if summary.exists():
        m = json.loads(summary.read_text())["metrics"]
        st.divider()
        st.markdown("**Ragas metrics** (this config)")
        c1, c2 = st.columns(2)
        c1.metric("Faithfulness", f"{m['faithfulness']:.2f}")
        c2.metric("Ctx recall", f"{m['context_recall']:.2f}")

    st.caption(
        "All manuals are public-domain U.S. Army technical manuals "
        "(17 U.S.C. § 105). Sources in `data/SOURCES.md`."
    )

# --------------------------------------------------------------------- messages
if "messages" not in st.session_state:
    st.session_state.messages = []

if not st.session_state.messages:
    big_wrench = ICON_WRENCH.replace('width="40" height="40"', 'width="56" height="56"')
    st.markdown(
        f'<div class="empty-wrap">{big_wrench}'
        "<h3>Ask the manuals</h3>"
        "<p>Questions are answered only from the seven indexed manuals, and every "
        "claim cites the manual and page it came from.</p></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(SUGGESTIONS))
    for col, s in zip(cols, SUGGESTIONS):
        if col.button(s, use_container_width=True):
            st.session_state.pending = s
            st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

# ------------------------------------------------------------------------ input
prompt = st.chat_input("Ask about the HMMWV, generator, forklift…")
if not prompt and "pending" in st.session_state:
    prompt = st.session_state.pop("pending")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the manuals…"):
                warm(config_name)
                from src.rag import stream_answer
                gen = stream_answer(prompt, config_name)
                kind, sources = next(gen)  # first yield is always the source list

            def deltas():
                for kind, chunk in gen:
                    if kind == "delta":
                        yield chunk

            text = st.write_stream(deltas())
            render_sources(sources)
            st.session_state.messages.append(
                {"role": "assistant", "content": text, "sources": sources}
            )
        except Exception:
            st.error(
                "Something went wrong while answering — most often a missing "
                "`ANTHROPIC_API_KEY` or a network hiccup. Check the key, then "
                "ask again; your question is kept in the box below.",
                icon="⚠️",
            )
            st.session_state.messages.pop()  # drop the unanswered user turn
