"""ManualMind — chat over Daimler Truck brand manuals with cited answers."""
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from src.config import BRANDS, CONFIGS, load_manifest

st.set_page_config(
    page_title="ManualMind — Daimler Truck Manuals",
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

# ------------------------------------------------------------------ design tokens
# Palette: "premium dark + action red" (ui-ux-pro-max, automotive) — slate
# structure, red accents. Type: IBM Plex Sans / JetBrains Mono (documentation
# pairing; display fonts rejected for a reading-heavy UI).
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --primary: #1E293B;      /* slate-800 */
  --primary-soft: #E9EDF1;
  --accent: #DC2626;       /* action red: 4.8:1 with white text */
  --fg: #0F172A;
  --fg-muted: #475569;
  --bg: #F8FAFC;
  --surface: #FFFFFF;
  --border: #E2E8F0;
  --radius: 12px;
}
html, body,
[data-testid="stAppViewContainer"] *:not([data-testid="stIconMaterial"]):not([class*="material-symbols"]) {
  font-family: 'IBM Plex Sans', sans-serif;
}
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
code, .mono { font-family: 'JetBrains Mono', monospace; }

/* chat bubbles: user = slate fill, assistant = white card */
[data-testid="stChatMessage"] {
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
}
[data-testid="stChatMessage"]:has(img[src*="E9EDF1"]) {
  background: var(--primary);
  border-color: var(--primary);
}
[data-testid="stChatMessage"]:has(img[src*="E9EDF1"]) p,
[data-testid="stChatMessage"]:has(img[src*="E9EDF1"]) li {
  color: #FFFFFF;
}
[data-testid="stChatMessage"] img[src^="data:image/svg"] {
  width: 32px; height: 32px; border-radius: 50%;
}

/* source cards */
.src-grid { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 8px 0; }
.src-card {
  flex: 1 1 240px; max-width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  padding: 8px 12px;
  transition: box-shadow 200ms ease;
}
.src-card:hover { box-shadow: 0 2px 8px rgba(15, 23, 42, 0.10); }
.src-card .brand {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
  color: var(--accent);
  text-transform: uppercase; letter-spacing: 0.05em;
}
.src-card .title { font-size: 13px; color: var(--fg); line-height: 1.5; font-weight: 500; }
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

/* sidebar: brand groups + manual list */
.brand-head {
  display: flex; align-items: center; gap: 8px;
  margin: 12px 0 6px 0;
}
.brand-head .chip {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; font-weight: 700; color: #FFFFFF;
  background: var(--accent); border-radius: 4px; padding: 2px 6px;
  letter-spacing: 0.04em;
}
.brand-head .name { font-size: 13px; font-weight: 600; color: var(--fg); }
.manual-item {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 8px 10px; margin-bottom: 6px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px;
}
.manual-item .m-title { font-size: 13px; font-weight: 500; color: var(--fg); line-height: 1.45; }
.manual-item .m-pages { font-size: 11px; color: var(--fg-muted); }
.manual-item svg { flex-shrink: 0; margin-top: 2px; }

/* empty state */
.empty-wrap { text-align: center; padding: 40px 16px 24px 16px; }
.empty-wrap h3 { font-weight: 600; color: var(--fg); margin: 16px 0 8px 0; }
.empty-wrap p { color: var(--fg-muted); font-size: 15px; line-height: 1.6; max-width: 46ch; margin: 0 auto; }

/* hero header */
.hero { display: flex; align-items: center; gap: 12px; padding: 8px 0 0 0; }
.hero .word { font-size: 26px; font-weight: 700; color: var(--fg); letter-spacing: -0.01em; }
.hero .word span { color: var(--accent); }
.hero .sub { font-size: 13px; color: var(--fg-muted); line-height: 1.5; }

.disclaimer { font-size: 11px; color: var(--fg-muted); line-height: 1.5; }

button:focus-visible { outline: 3px solid #2563EB !important; outline-offset: 2px; }
[data-testid="stChatInput"] textarea { font-size: 16px; }

@media (prefers-reduced-motion: reduce) {
  * { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

ICON_BOOK = """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1E293B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="manual"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>"""
ICON_TRUCK = """<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#1E293B" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="ManualMind"><path d="M10 17h4V5H2v12h3"/><path d="M20 17h2v-3.34a4 4 0 0 0-1.17-2.83L19 9h-5v8h1"/><circle cx="7.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>"""
ICON_CITE = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>"""

AVATAR_USER = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<rect width='24' height='24' rx='12' fill='%23E9EDF1'/>"
    "<circle cx='12' cy='9.5' r='3.5' fill='%231E293B'/>"
    "<path d='M5 20c1.5-3.5 4-5 7-5s5.5 1.5 7 5' fill='%231E293B'/></svg>"
)
AVATAR_BOT = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<rect width='24' height='24' rx='12' fill='%231E293B'/>"
    "<path d='M9.5 15.5h3v-7H5v7h2' fill='none' stroke='white' stroke-width='1.4'/>"
    "<path d='M15.5 15.5h1.5v-2.2a2.6 2.6 0 0 0-.76-1.84L15 10.2h-2.5v5.3h.8' "
    "fill='none' stroke='white' stroke-width='1.4'/>"
    "<circle cx='8.6' cy='15.8' r='1.5' fill='none' stroke='white' stroke-width='1.4'/>"
    "<circle cx='14.4' cy='15.8' r='1.5' fill='none' stroke='white' stroke-width='1.4'/></svg>"
)

# Plain-language names for the retrieval configs (measured with Ragas; the
# technical details live in the README, not in the sidebar).
SEARCH_MODES = {
    "Best quality (recommended)": {
        "config": "reranker",
        "hint": "Looks at 20 possible passages, keeps the 4 best. Most accurate in our tests.",
    },
    "Fastest": {
        "config": "baseline",
        "hint": "Straightforward meaning-based search. Quickest answers.",
    },
    "Exact words + meaning": {
        "config": "hybrid",
        "hint": "Also matches exact part numbers and codes, not just meaning.",
    },
}

SUGGESTIONS = [
    "What do I need to do before tilting the Cascadia's hood?",
    "Can I run biodiesel in a FUSO FE?",
    "What training is required to work on the eCascadia's electrical system?",
]


@st.cache_resource(show_spinner=False)
def warm(config_name: str) -> bool:
    from src.rag import _vectorstore
    _vectorstore(CONFIGS[config_name].index_name)
    return True


def render_sources(sources: list[dict]) -> None:
    cards = "".join(
        f'<div class="src-card">'
        f'<span class="badge">p.{s["page"]}</span>'
        f'<div class="brand">{s.get("brand", "")}</div>'
        f'<div class="title">{s["manual"]}</div>'
        f'<div class="snippet">{s["snippet"]}</div>'
        f"</div>"
        for s in sources
    )
    st.markdown(
        f'<div class="src-label">{ICON_CITE} From the manuals</div>'
        f'<div class="src-grid">{cards}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(
        f'<div class="hero">{ICON_TRUCK}<div><div class="word">Manual<span>Mind</span></div>'
        '<div class="sub">Daimler Truck brand manuals — cited answers</div></div></div>',
        unsafe_allow_html=True,
    )
    st.divider()

    manifest = load_manifest()
    st.markdown(f"**Manuals in the knowledge base** · {len(manifest)}")
    by_brand: dict[str, list[dict]] = {}
    for m in manifest:
        by_brand.setdefault(m["brand"], []).append(m)
    for brand, items in by_brand.items():
        words = brand.split()
        chip = (words[0][:2] if len(words) == 1
                else "".join(w[0] for w in words[:2])).upper()
        st.markdown(
            f'<div class="brand-head"><span class="chip">{chip}</span>'
            f'<span class="name">{brand}</span></div>'
            + "".join(
                f'<div class="manual-item">{ICON_BOOK}<div>'
                f'<div class="m-title">{m["title"]}</div></div></div>'
                for m in items
            ),
            unsafe_allow_html=True,
        )

    st.divider()
    with st.expander("Add a manual"):
        st.caption("Upload a PDF (with selectable text) and it becomes part of "
                   "the knowledge base immediately.")
        up_brand = st.selectbox("Brand", BRANDS, key="up_brand")
        up_title = st.text_input("Manual name", placeholder="e.g. Econic — Operator's Manual")
        up_file = st.file_uploader("PDF file", type=["pdf"], key="up_file")
        if st.button("Add to knowledge base", type="primary",
                     disabled=not (up_file and up_title.strip())):
            from src.ingest import add_manual
            try:
                with st.spinner("Reading, chunking, and indexing — about a minute…"):
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                        tf.write(up_file.getvalue())
                    stats = add_manual(tf.name, up_brand, up_title.strip())
                    os.unlink(tf.name)
                st.cache_resource.clear()  # reload vector stores with new chunks
                st.success(f"Added “{up_title.strip()}” — {stats['pages']} pages indexed.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception:
                st.error("Couldn't index that PDF. Check it opens normally and "
                         "has selectable text, then try again.")

    with st.expander("Search settings"):
        mode = st.radio("How should answers be found?", list(SEARCH_MODES),
                        label_visibility="collapsed")
        st.caption(SEARCH_MODES[mode]["hint"])
    config_name = SEARCH_MODES[mode]["config"]

    results_dir = Path(__file__).parent / "evals" / "results"
    summary = results_dir / f"{config_name}_summary.json"
    if summary.exists():
        m = json.loads(summary.read_text())["metrics"]
        st.divider()
        st.markdown("**Measured accuracy** (Ragas)")
        c1, c2 = st.columns(2)
        c1.metric("Sticks to the manuals", f"{m['faithfulness']:.0%}",
                  help="Faithfulness: how often every claim in an answer is backed by the retrieved manual text.")
        c2.metric("Finds the right pages", f"{m['context_recall']:.0%}",
                  help="Context recall: how often the pages needed to answer were actually retrieved.")

    st.divider()
    st.markdown(
        '<p class="disclaimer">Personal learning project. Not affiliated with or '
        "endorsed by Daimler Truck AG. Manuals are publicly distributed by their "
        "manufacturers; sources and copyright notes in the repo's "
        "<code>data/manuals.json</code>.</p>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------- messages
if "messages" not in st.session_state:
    st.session_state.messages = []

if not st.session_state.messages:
    big_truck = ICON_TRUCK.replace('width="40" height="40"', 'width="56" height="56"')
    st.markdown(
        f'<div class="empty-wrap">{big_truck}'
        "<h3>Ask the manuals</h3>"
        "<p>Answers come only from the indexed Freightliner, Western Star, FUSO, "
        "and Mercedes-Benz truck manuals — and every claim shows the manual and "
        "page it came from.</p></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(SUGGESTIONS))
    for col, s in zip(cols, SUGGESTIONS):
        if col.button(s, use_container_width=True):
            st.session_state.pending = s
            st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=AVATAR_USER if msg["role"] == "user" else AVATAR_BOT):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

# ------------------------------------------------------------------------ input
prompt = st.chat_input("Ask about the Cascadia, Actros, FUSO FE, 47X…")
if not prompt and "pending" in st.session_state:
    prompt = st.session_state.pop("pending")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATAR_USER):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AVATAR_BOT):
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
                "ask again.",
                icon="⚠️",
            )
            st.session_state.messages.pop()
