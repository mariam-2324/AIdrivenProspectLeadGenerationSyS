"""Streamlit UI: AI-Driven Prospecting & Lead Extraction System."""
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # Local run ke waqt .env se keys load karega

LLM_ENV_KEYS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_FALLBACK_MODELS",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "LLM_PROVIDER",
)


def get_secret_value(key_name: str):
    """Pehle Streamlit Cloud Secrets check karega, warna .env / OS environment se lega."""
    try:
        if key_name in st.secrets:
            return st.secrets[key_name]
    except Exception:
        pass
    return os.getenv(key_name)


# Cloud Secrets ko os.environ mein copy karein taake extractor.py aur baqi modules use kar sakein
for env_key in LLM_ENV_KEYS:
    secret_val = get_secret_value(env_key)
    if secret_val is not None and str(secret_val).strip() != "":
        os.environ[env_key] = str(secret_val).strip()

from sources import load_sample, fetch_hackernews, find_website_osm, fetch_website_text
from extractor import extract, pick_provider
from analytics import build_dataframe

st.set_page_config(page_title="AI Lead Extraction", page_icon="🎯", layout="wide")
st.title("🎯 AI-Driven Prospecting & Lead Extraction")
st.caption("Text of business or Website -> LLM -> requirements, buying signals, website gaps -> lead score")

# Optional password (Secrets mein APP_PASSWORD set ho to hi poochha jayega)
_pw = _secret("APP_PASSWORD")
if _pw and st.text_input("Password", type="password") != _pw:
    st.info("Password daal kar aage barhein.")
    st.stop()

provider = pick_provider()
if provider == "offline":
    st.warning("No LLM API key found: Only basic offline rules will be run.")
else:
    st.sidebar.success(f"LLM provider: {provider}")

mode = st.radio("Source", ["Business / Website", "Hacker News search", "Sample data"], horizontal=True)

listings = []
run = False
if mode == "Business / Website":
    c1, c2 = st.columns(2)
    name = c1.text_input("Business name", placeholder="ECOM Deals Karachi")
    url = c2.text_input("Website URL (optional, warna OpenStreetMap se dhoondhenge)", placeholder="https://example.com")
    focus = st.text_input("Focus (optional)", placeholder="website text and copywriting quality: is there room for improvement?")
    run = st.button("Analyze", type="primary")
    if run:
        if not (name or url):
            st.error("put Business name or url.")
            st.stop()
        try:
            with st.spinner("Finding the Website..."):
                site = url or find_website_osm(name)
                if not site:
                    st.error("Website OpenStreetMap par nahi mili. URL khud dein.")
                    st.stop()
                text = fetch_website_text(site)
            listings = [{"id": 1, "source": f"website:{site}", "company": name or site,
                         "text": text, "focus": focus or None}]
        except Exception as e:
            st.error(f"Website lane mein masla: {e}")
            st.stop()
elif mode == "Hacker News search":
    c1, c2 = st.columns([3, 1])
    q = c1.text_input("Search words", value="looking for developer")
    limit = c2.number_input("Limit", 1, 30, 10)
    run = st.button("Search & Analyze", type="primary")
    if run:
        try:
            with st.spinner("Hacker News se data aa raha hai..."):
                listings = fetch_hackernews(q, int(limit))
        except Exception as e:
            st.error(f"API masla: {e}")
            st.stop()
else:
    run = st.button("Run on sample data", type="primary")
    if run:
        listings = load_sample()

if run:
    if not listings:
        st.warning("Koi listing nahi mili.")
        st.stop()
    with st.spinner("LLM analysis ho rahi hai..."):
        results = [extract(l, provider) for l in listings]
    df = build_dataframe(listings, results)

    qualified = int((df["score"] >= 30).sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Total", len(df))
    m2.metric("Qualified (score >= 30)", qualified)
    m3.metric("Hot leads", int((df["tier"] == "Hot").sum()))

    view = df[["company", "industry", "requirement", "urgency", "score", "tier"]].copy()
    st.dataframe(view)

    st.subheader("Details")
    for l, r in zip(listings, results):
        with st.expander(f"{l['company']}"):
            st.write("**Industry:**", r["industry"])
            st.write("**Requirement:**", r["requirement"] or "-")
            st.write("**Buying signals:**", ", ".join(r["buying_signals"]) or "-")
            st.write("**Website gaps / findings:**", ", ".join(r["website_gaps"]) or "-")
            st.write("**Outreach angle:**", r["outreach_angle"])

    export = df.copy()
    for col in ("buying_signals", "website_gaps"):
        export[col] = export[col].apply(lambda x: ", ".join(x))
    st.download_button("Download CSV", export.to_csv(index=False), "qualified_leads.csv", "text/csv")