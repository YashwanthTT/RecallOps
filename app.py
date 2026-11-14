"""Streamlit UI for the Incident Memory Agent.

Run with: streamlit run app.py
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

try:
    from src.core.agent import parse_incident, run_agent
    from src.core.memory import Memory, MemoryStore
    from src.core.seed_data import (
        DEMO_ALERTS,
        INCIDENTS,
        POLICIES,
        incident_to_document,
        policy_to_document,
    )
    from src.integrations.oneuptime import (
        SAMPLE_PAYLOAD,
        SIMULATED_SCENARIOS,
        OneUptimeIncident,
        ProbeResult,
        create_incident_from_probe,
        create_incident_from_scenario,
        incident_to_document as oneuptime_to_document,
        parse_oneuptime,
        probe_endpoint,
    )
except ImportError:
    from agent import parse_incident, run_agent
    from memory import Memory, MemoryStore
    from oneuptime import (
        SAMPLE_PAYLOAD,
        SIMULATED_SCENARIOS,
        OneUptimeIncident,
        ProbeResult,
        create_incident_from_probe,
        create_incident_from_scenario,
        incident_to_document as oneuptime_to_document,
        parse_oneuptime,
        probe_endpoint,
    )
    from seed_data import (
        DEMO_ALERTS,
        INCIDENTS,
        POLICIES,
        incident_to_document,
        policy_to_document,
    )

load_dotenv()


def _load_streamlit_secrets() -> None:
    """Map Streamlit Cloud secrets into env vars for the shared modules."""
    for key in (
        "GROQ_API_KEY",
        "GROQ_BASE_URL",
        "LLM_MODEL",
        "HINDSIGHT_BASE_URL",
        "HINDSIGHT_API_KEY",
        "HINDSIGHT_BANK_ID",
    ):
        if os.getenv(key):
            continue
        try:
            value = st.secrets[key]
        except Exception:
            continue
        if value:
            os.environ[key] = str(value)


_load_streamlit_secrets()

st.set_page_config(
    page_title="Incident Memory Agent — Northwind Pay",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------- design system
# One CSS block, one token set. Font overrides are scoped to text elements so
# Streamlit's Material Symbols icon font is never replaced by Inter.
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      :root {
        --bg: #F8F6F0;                /* Warm off-white / ecru */
        --surface: #FFFFFF;           /* Crisp clean ivory/white card surface */
        --surface-2: #F2EFE8;         /* Soft warm beige for secondary blocks & inputs */
        --surface-3: #E8E3D8;         /* Deeper beige for hover & active states */
        --border: #E4DFD5;            /* Warm beige border */
        --border-strong: #CEC7BA;     /* Defined beige/stone border */
        --text: #1C1917;              /* Deep warm stone / near black for great legibility */
        --text-muted: #57534E;        /* Warm medium stone */
        --text-faint: #78716C;        /* Soft warm stone */
        --accent: #EA580C;            /* Energetic warm orange */
        --accent-strong: #C2410C;     /* Deep rich burnt orange */
        --accent-button: #EA580C;     /* Orange button highlight */
        --accent-soft: rgba(234, 88, 12, .10); /* Soft orange tint */
        --green: #16A34A;
        --green-text: #15803D;
        --green-soft: rgba(22, 163, 74, .10);
        --red: #DC2626;
        --red-text: #B91C1C;
        --red-soft: rgba(220, 38, 38, .09);
        --amber: #D97706;
        --amber-text: #B45309;
        --amber-soft: rgba(217, 119, 6, .10);
        --blue: #2563EB;
        --blue-text: #1D4ED8;
        --blue-soft: rgba(37, 99, 235, .09);
        --radius: 12px;
        --radius-sm: 8px;
        --radius-lg: 20px;
        --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        --mono: 'SFMono-Regular', ui-monospace, 'Cascadia Code', Menlo, monospace;
        --space-1: 8px;
        --space-2: 16px;
        --space-3: 24px;
        --space-4: 32px;
      }

      html, body, .stApp, button, input, textarea, select,
      [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"],
      [data-testid="stCaptionContainer"], [data-testid="stMetricLabel"],
      [data-testid="stMetricValue"], [data-testid="stChatMessage"] {
        font-family: var(--font);
      }

      /* Never let a text font override the icon font. */
      [data-testid="stIconMaterial"], .material-symbols-rounded,
      .material-icons, [class*="material-symbols"] {
        font-family: 'Material Symbols Rounded' !important;
        font-weight: normal !important;
        font-style: normal !important;
        letter-spacing: normal !important;
        text-transform: none !important;
      }

      .stApp { background: var(--bg); }
      [data-testid="stMainBlockContainer"] {
        max-width: 1140px;
        width: calc(100% - 24px);
        box-sizing: border-box;
        padding: 32px 32px 48px;
        margin: 12px auto 24px;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: none;
      }
      [data-testid="stSidebar"] { background: #F7F6F3; border-right: 1px solid var(--border); }
      [data-testid="stSidebarUserContent"] { padding-top: 12px; }

      /* Hide Streamlit chrome while keeping sidebar controls fully functional. */
      [data-testid="stDecoration"], [data-testid="stStatusWidget"],
      [data-testid="stAppDeployButton"], [data-testid="stToolbarActions"],
      #MainMenu, footer { display: none !important; }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stToolbar"] { background: transparent !important; right: 0; }
      [data-testid="stExpandSidebarButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        color: var(--text) !important;
      }
      iframe[title="streamlit.components.v1.html"] {
        position: absolute !important;
        height: 0 !important;
        width: 0 !important;
        border: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
      }

      /* ---- type scale: 32 / 20 / 15 / 12 ---- */
      .page-title {
        font-size: 28px !important; line-height: 1.2; letter-spacing: -.03em;
        font-weight: 700; color: var(--text); margin: 0 0 8px;
      }
      .page-sub { font-size: 15px; line-height: 1.6; color: var(--text-muted); margin: 0 0 20px; max-width: 820px; }
      .eyebrow {
        font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
        color: var(--accent); margin: 0 0 8px;
      }
      h1, h2, h3, h4, h5, h6 { color: var(--text) !important; font-family: var(--font) !important; }
      h1 { font-size: 32px !important; }
      h2 { font-size: 20px !important; line-height: 1.3; margin: 0 0 4px !important; }
      h3 { font-size: 16px !important; margin: 0 0 4px !important; }
      p, li { font-size: 15px; line-height: 1.62; color: var(--text-muted); }
      [data-testid="stCaptionContainer"] p, .stCaption p { font-size: 12px !important; line-height: 1.5; color: var(--text-faint) !important; }
      [data-testid="stMarkdownContainer"] strong { color: var(--text); }

      /* ---- nav bar ---- */
      .st-key-nav [data-testid="stButtonGroup"] {
        background: var(--surface-2);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 4px;
        gap: 2px;
        flex-wrap: wrap;
        height: auto !important;
      }
      .st-key-nav [data-testid="stButtonGroup"] button {
        border: 0 !important;
        border-radius: 6px !important;
        color: var(--text-muted) !important;
        background: transparent !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        padding: 6px 14px !important;
        min-height: 34px !important;
        transition: all 0.15s ease-in-out !important;
      }
      .st-key-nav [data-testid="stButtonGroup"] button:hover {
        color: var(--text) !important;
        background: var(--surface-3) !important;
      }
      .st-key-nav [data-testid="stButtonGroup"] button[aria-checked="true"],
      .st-key-nav [data-testid="stButtonGroup"] button[aria-pressed="true"],
      .st-key-nav [data-testid="stButtonGroup"] button[data-selected="true"] {
        color: #FFFFFF !important;
        background: var(--accent) !important;
        box-shadow: none;
      }
      .st-key-nav [data-testid="stButtonGroup"] button[aria-checked="true"] p,
      .st-key-nav [data-testid="stButtonGroup"] button[aria-pressed="true"] p,
      .st-key-nav [data-testid="stButtonGroup"] button[data-selected="true"] p {
        color: #FFFFFF !important;
      }

      /* Suggested-question chips (st.pills), not the nav bar. */
      .st-key-reflect_pills [data-testid="stButtonGroup"] {
        display: flex; flex-wrap: wrap; gap: 6px;
        background: transparent; border: 0; padding: 0;
      }
      .st-key-reflect_pills [data-testid="stButtonGroup"] button {
        border: 1px solid var(--border-strong) !important;
        border-radius: 6px !important;
        background: var(--surface) !important;
        color: var(--text-muted) !important;
        font-size: 13px !important;
        font-weight: 550 !important;
        padding: 6px 12px !important;
        min-height: 34px !important;
      }
      .st-key-reflect_pills [data-testid="stButtonGroup"] button:hover {
        border-color: var(--accent) !important;
        color: var(--accent) !important;
      }
      .st-key-reflect_pills [data-testid="stButtonGroup"] button[aria-checked="true"] {
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
        color: var(--accent) !important;
      }

      /* ---- cards ---- */
      [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface);
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        box-shadow: none;
      }
      [data-testid="stVerticalBlockBorderWrapper"] > div { padding: 2px; }

      .section-head {
        display: flex; align-items: flex-start; justify-content: space-between;
        gap: var(--space-2); margin: 16px 0 12px;
      }
      .section-title { font-size: 20px; font-weight: 650; letter-spacing: -.02em; color: var(--text); margin: 0; }
      .section-sub { font-size: 12px; color: var(--text-faint); margin-top: 2px; }
      .mini-head { font-size: 13px; font-weight: 700; letter-spacing: .02em; color: var(--text); margin: 14px 0 6px; }
      .muted { color: var(--text-faint); }

      /* ---- chips / pills ---- */
      .chip {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 3px 9px; border-radius: 999px;
        font-size: 12px; font-weight: 650; line-height: 1.5;
        border: 1px solid var(--border-strong); color: var(--text-muted);
        background: var(--surface-2); white-space: nowrap;
      }
      .chip.green { color: var(--green-text); background: var(--green-soft); border-color: rgba(22, 163, 74, .28); }
      .chip.red { color: var(--red-text); background: var(--red-soft); border-color: rgba(220, 38, 38, .28); }
      .chip.amber { color: var(--amber-text); background: var(--amber-soft); border-color: rgba(217, 119, 6, .28); }
      .chip.blue { color: var(--blue-text); background: var(--blue-soft); border-color: rgba(37, 99, 235, .28); }
      .chip.indigo { color: var(--accent); background: var(--accent-soft); border-color: rgba(234, 88, 12, .28); }
      .chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
      .hint-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 12px; color: var(--text-faint); }

      /* ---- sidebar ---- */
      .brand { font-size: 16px; font-weight: 700; color: var(--text); letter-spacing: -.01em; }
      .brand-sub { font-size: 12px; color: var(--text-faint); margin-top: 2px; }
      .status-card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 12px; margin: 12px 0 4px;
        box-shadow: none;
      }
      .status-row { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 650; color: var(--text); }
      .dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
      .dot.green { background: var(--green); box-shadow: none; }
      .dot.red { background: var(--red); box-shadow: none; }
      .status-host { font-size: 12px; color: var(--text-faint); margin: 6px 0 8px 16px; }
      .bank-chip {
        display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        font-family: var(--mono); font-size: 11px; color: var(--accent-strong);
        background: var(--accent-soft); border: 1px solid rgba(234, 88, 12, .24);
        border-radius: 6px; padding: 4px 7px;
      }
      .metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 8px 0 4px; }
      .metric-card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 10px; padding: 8px 8px 7px; text-align: center;
        box-shadow: none;
      }
      .metric-value { display: block; font-size: 20px; font-weight: 700; color: var(--text); line-height: 1.15; }
      .metric-label { display: block; font-size: 10px; color: var(--text-faint); text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }
      .memory-how { display: grid; gap: 7px; margin-top: 6px; }
      .memory-how-row { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-muted); line-height: 1.45; }
      .memory-how-icon { width: 18px; text-align: center; flex: 0 0 18px; }
      .memory-how-row code {
        font-family: var(--mono); font-size: 11px; color: var(--accent-strong);
        background: var(--accent-soft); border: 1px solid rgba(234, 88, 12, .24);
        border-radius: 5px; padding: 1px 5px;
      }
      .success-card {
        background: var(--green-soft); border: 1px solid rgba(22, 163, 74, .28);
        border-radius: var(--radius); padding: 12px 14px; font-size: 13px; color: var(--green-text);
      }
      .error-card {
        background: var(--red-soft); border: 1px solid rgba(220, 38, 38, .28);
        border-radius: var(--radius); padding: 12px 14px; font-size: 13px; color: var(--red-text);
      }
      .error-card .error-title { font-weight: 700; color: var(--text); margin-bottom: 4px; }
      .error-card .error-body { color: var(--red-text); font-size: 12px; line-height: 1.5; word-break: break-word; }

      /* ---- hero / empty state ---- */
      .st-key-hero_card [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface-2);
        border-color: rgba(234, 88, 12, .26) !important;
      }
      .hero-kicker { font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: var(--accent); }
      .hero-title { font-size: 26px; font-weight: 700; letter-spacing: -.02em; color: var(--text); margin: 6px 0 6px; }
      .hero-body { font-size: 14px; line-height: 1.6; color: var(--text-muted); max-width: 720px; margin: 0 0 12px; }
      .hero-stats { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px; }
      .ready-strip {
        display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
        background: var(--surface-2); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 10px 12px; margin: 4px 0 12px;
        font-size: 13px; color: var(--text-muted);
      }

      /* ---- briefing ---- */
      .st-key-impact_strip { position: sticky; top: 8px; z-index: 20; }
      .st-key-impact_strip [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, .96);
        backdrop-filter: blur(12px);
        border-color: var(--border-strong) !important;
        box-shadow: none;
      }
      .impact-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
      .impact-item { padding: 2px 6px; }
      .impact-value { font-size: 18px; font-weight: 700; color: var(--text); line-height: 1.2; }
      .impact-label { font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }
      .st-key-without_card [data-testid="stVerticalBlockBorderWrapper"] { border-color: rgba(220, 38, 38, .30) !important; background: var(--surface); }
      .st-key-with_card [data-testid="stVerticalBlockBorderWrapper"] { border-color: rgba(22, 163, 74, .30) !important; background: var(--surface); }

      .avoid-head { display: flex; align-items: center; gap: 8px; margin: 8px 0 8px; }
      .avoid-head .title { font-size: 16px; font-weight: 700; color: var(--red-text); }
      .avoid-card {
        display: flex; gap: 10px; align-items: flex-start;
        background: var(--red-soft); border: 1px solid rgba(220, 38, 38, .28);
        border-radius: var(--radius); padding: 10px 12px; margin: 6px 0;
        font-size: 13px; line-height: 1.5; color: var(--text);
      }
      .avoid-icon { flex: 0 0 18px; text-align: center; color: var(--red); }
      .avoid-empty {
        background: var(--green-soft); border: 1px solid rgba(22, 163, 74, .28);
        border-radius: var(--radius); padding: 10px 12px; font-size: 13px; color: var(--green-text);
      }
      .step-line { display: flex; gap: 8px; align-items: flex-start; margin: 8px 0 4px; font-size: 14px; line-height: 1.5; color: var(--text); }
      .step-num {
        flex: 0 0 20px; width: 20px; height: 20px; border-radius: 999px;
        display: inline-flex; align-items: center; justify-content: center;
        background: var(--accent-soft); color: var(--accent-strong); font-size: 11px; font-weight: 700;
      }
      .incident-row { display: flex; gap: 8px; align-items: flex-start; margin: 5px 0; font-size: 13px; line-height: 1.5; color: var(--text-muted); }
      .escalate-card {
        background: var(--amber-soft); border: 1px solid rgba(217, 119, 6, .28);
        border-radius: var(--radius); padding: 10px 12px; margin-top: 10px;
      }
      .escalate-card ul { margin: 4px 0 0; padding-left: 18px; }
      .escalate-card li { color: var(--amber-text); font-size: 13px; margin: 3px 0; }

      /* ---- preset cards ---- */
      [class*="st-key-preset_"] [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface); height: 100%;
        border-color: var(--border) !important;
      }
      [class*="st-key-preset_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--accent) !important;
        box-shadow: none;
      }
      .preset-title { font-size: 14px; font-weight: 650; color: var(--text); line-height: 1.35; margin: 8px 0 4px; min-height: 40px; }
      [class*="st-key-preset_"] { height: 100%; }
      [class*="st-key-preset_"] [data-testid="stVerticalBlock"] { gap: 12px; }
      [data-testid="stHorizontalBlock"] { align-items: stretch; }
      .st-key-nav { margin-bottom: 8px; }
      .status-card { margin-top: 20px; }
      .section-head > div:first-child { min-width: 0; }
      @media (prefers-reduced-motion: reduce) {
        button { transition: none !important; transform: none !important; }
      }

      /* ---- stepper ---- */
      .stepper { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 16px; }
      .step-pill {
        display: flex; align-items: center; gap: 8px; padding: 7px 12px;
        border: 1px solid var(--border); border-radius: 999px; background: var(--surface);
        font-size: 12px; font-weight: 650; color: var(--text-faint);
        box-shadow: none;
      }
      .step-pill .n {
        width: 18px; height: 18px; border-radius: 999px; display: inline-flex;
        align-items: center; justify-content: center; font-size: 10px; font-weight: 700;
        background: var(--surface-2); color: var(--text-muted);
      }
      .step-pill.active { border-color: rgba(234, 88, 12, .45); color: var(--accent-strong); background: var(--accent-soft); }
      .step-pill.active .n { background: var(--accent); color: #FFFFFF; }
      .step-pill.done { border-color: rgba(22, 163, 74, .32); color: var(--green-text); background: var(--green-soft); }
      .step-pill.done .n { background: var(--green); color: #FFFFFF; }

      /* ---- native widgets & orange button highlights ---- */
      [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
        background: var(--accent) !important;
        border: 1px solid #EA580C !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        font-weight: 650 !important;
        font-size: 14px !important;
        min-height: 40px;
        box-shadow: none;
        transition: all 0.15s ease-in-out !important;
      }
      [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
        background: var(--accent-strong) !important;
        box-shadow: none;
        transform: translateY(-1px);
      }
      [data-testid="stBaseButton-primary"]:active, [data-testid="stBaseButton-primaryFormSubmit"]:active {
        transform: translateY(0);
      }
      [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {
        background: var(--surface) !important;
        border: 1px solid var(--border-strong) !important;
        color: var(--text) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        min-height: 40px;
        box-shadow: none;
        transition: all 0.15s ease-in-out !important;
      }
      [data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover {
        border-color: #EA580C !important;
        color: #EA580C !important;
        background: rgba(234, 88, 12, 0.06) !important;
        box-shadow: none;
      }
      /* Button labels inherit the button colour instead of the muted paragraph colour. */
      [data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p { color: #FFFFFF !important; }
      [data-testid="stBaseButton-secondary"] p, [data-testid="stBaseButton-secondaryFormSubmit"] p { color: inherit !important; }
      .st-key-nav [data-testid="stButtonGroup"] button p,
      .st-key-reflect_pills [data-testid="stButtonGroup"] button p { color: inherit !important; }
      [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text) !important;
      }
      [data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
      [data-baseweb="select"] > div:focus-within {
        border-color: var(--accent) !important;
        box-shadow: none;
      }
      input, textarea { font-size: 14px !important; color: var(--text) !important; }
      label, [data-testid="stWidgetLabel"] p { font-size: 13px !important; color: var(--text-muted) !important; font-weight: 500; }

      /* Inline code becomes a readable chip, not 0.82em text. */
      p code, li code, td code {
        font-family: var(--mono); font-size: 12px;
        color: var(--accent-strong); background: var(--accent-soft);
        border: 1px solid rgba(234, 88, 12, .22);
        border-radius: 6px; padding: 1px 6px;
      }
      [data-testid="stCode"] {
        margin: 4px 0 8px;
        max-width: 100%;
        min-width: 0;
      }
      [data-testid="stCode"] pre {
        background: #23201D !important;
        border: 1px solid #3E3832 !important;
        border-radius: 10px !important;
        font-size: 12.5px !important;
        color: #F8F6F0 !important;
        max-width: 100%;
      }
      [data-testid="stCode"] code {
        white-space: pre-wrap !important;
        word-break: break-word;
        color: #F8F6F0 !important;
      }
      [data-testid="stMain"] [data-testid="column"] { min-width: 0; }

      /* Focus states for keyboard users. */
      button:focus-visible, a:focus-visible, input:focus-visible,
      textarea:focus-visible, select:focus-visible, summary:focus-visible {
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
      }

      /* ---- expanders ---- */
      [data-testid="stExpander"] {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        background: var(--surface) !important;
        box-shadow: none;
        margin: 6px 0;
      }
      [data-testid="stExpander"] summary { font-size: 13px !important; font-weight: 600; color: var(--text); padding: 8px 12px; }
      [data-testid="stExpander"] summary:hover { color: var(--accent); }

      /* ---- tabs inside the integration guide ---- */
      [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 8px;
      }
      [data-testid="stTabs"] [data-baseweb="tab"] {
        height: 36px; padding: 0 12px; border-radius: 8px 8px 0 0;
        color: var(--text-muted); font-weight: 600; font-size: 13px;
      }
      [data-testid="stTabs"] [aria-selected="true"] { color: var(--accent-strong); border-bottom: 2px solid var(--accent); background: var(--accent-soft); }

      [data-testid="stAlert"] { border-radius: var(--radius) !important; }
      [data-testid="stMetricValue"] { font-size: 20px; color: var(--text); }

      @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"] { width: calc(100% - 16px); margin: 8px auto; padding: 18px 16px 36px; }
        .page-title { font-size: 26px !important; }
        .impact-grid { grid-template-columns: repeat(2, 1fr); }
        .metric-grid { grid-template-columns: repeat(3, 1fr); }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 12px; }
        [data-testid="stMain"] [data-testid="stColumn"] { min-width: 100% !important; flex: 1 1 100% !important; }
        [data-testid="stButtonGroup"] { border-radius: 14px; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

components.html(
    """
    <script>
      (function() {
        function openSidebar() {
          try {
            const doc = window.parent.document;
            const expandBtn = doc.querySelector('[data-testid="stExpandSidebarButton"]');
            if (expandBtn) {
              expandBtn.click();
            }
            for (let i = 0; i < window.parent.localStorage.length; i++) {
              const key = window.parent.localStorage.key(i);
              if (key && key.startsWith("stSidebarCollapsed")) {
                window.parent.localStorage.setItem(key, "false");
              }
            }
          } catch (e) {}
        }
        openSidebar();
        setTimeout(openSidebar, 150);
        setTimeout(openSidebar, 450);
      })();
    </script>
    """,
    height=0,
    width=0,
)

REFLECT_PRESETS = [
    "Which services have recurring failures, and what keeps recurring?",
    "Which remediation actions have repeatedly made things worse?",
    "What should a new on-call engineer know about checkout-api?",
]
CUSTOM = "Custom alert"

NAV_ITEMS = [
    ("Briefing", "briefing"),
    ("Service monitor", "monitor"),
    ("OneUptime intake", "intake"),
    ("Close the loop", "close"),
    ("Reflect", "reflect"),
    ("Integration guide", "guide"),
]
NAV_LABELS = [label for label, _ in NAV_ITEMS]
NAV_SLUG = dict(NAV_ITEMS)
SLUG_LABEL = {slug: label for label, slug in NAV_ITEMS}

PRESET_META = {
    "checkout-api 502 spike (connection pool)": (
        "checkout-api",
        "502 spike after v3.4.1",
        "Connection pool exhaustion from a blocking FX call.",
        "Sev 1",
    ),
    "payments-gateway mTLS failures (certificate)": (
        "payments-gateway",
        "mTLS handshake failures",
        "Expired client certificate rejected by the PSP.",
        "Sev 1",
    ),
    "orders-db recovery conflict (replica)": (
        "orders-db",
        "Recovery conflict on replica",
        "Reporting query blocks WAL replay and cancels reads.",
        "Sev 2",
    ),
    "kafka-ingest consumer lag (hot partition)": (
        "kafka-ingest",
        "Consumer lag on hot partitions",
        "Two partitions carry 61% of payment events.",
        "Sev 2",
    ),
}


def esc(value: Any) -> str:
    return html.escape(str(value))


def chip(text: str, tone: str = "", icon: str = "") -> str:
    prefix = f"{icon} " if icon else ""
    return f'<span class="chip {tone}">{prefix}{esc(text)}</span>'


def _short_host(base_url: str) -> str:
    parsed = urlparse(base_url or "")
    return parsed.netloc or (base_url or "unknown")


@st.cache_resource
def get_store() -> MemoryStore:
    """Create one memory store per Streamlit process and probe the backend."""
    store = MemoryStore()
    store.connect()
    return store


def seed_memories(store: MemoryStore, progress: Any | None = None) -> tuple[int, int, list[str]]:
    """Retain every incident and policy. Returns (documents, incidents, errors)."""
    items: list[tuple[str, str, str, str]] = []
    for incident in INCIDENTS:
        items.append(
            (
                incident_to_document(incident),
                f"past incident {incident['id']} on {incident['service']}",
                incident["date"],
                f"incident-{incident['id']}",
            )
        )
    for policy in POLICIES:
        items.append(
            (
                policy_to_document(policy),
                f"team policy {policy['id']}",
                policy["date"],
                f"policy-{policy['id']}",
            )
        )

    errors: list[str] = []
    stored = 0
    store.configure_bank()
    for index, (content, context, timestamp, document_id) in enumerate(items, 1):
        try:
            store.retain(
                content,
                context=context,
                timestamp=timestamp,
                document_id=document_id,
                update_mode="replace",
            )
            stored += 1
        except Exception as exc:  # one bad document must not abort the seed
            errors.append(f"{context}: {type(exc).__name__}: {exc}")
        if progress is not None:
            progress.progress(
                index / len(items),
                text=f"Retaining {index}/{len(items)} — {context}",
            )
    return stored, len(INCIDENTS), errors


def outcome_document(
    service: str,
    title: str,
    root_cause: str,
    fixed: str,
    failed: str,
    ttr_minutes: int,
    resolver: str,
    severity: str = "Sev 2",
) -> tuple[str, str]:
    """Render a just-closed incident as a memory document, with a fresh ID."""
    now = datetime.now(timezone.utc)
    incident_id = f"INC-{now:%y%m%d%H%M%S}"
    failed_items = [part.strip() for part in failed.replace("\n", ";").split(";") if part.strip()]
    failed_block = "\n".join(f"- {item}" for item in failed_items) if failed_items else "- None recorded."
    fixed_one_line = " ".join(fixed.split())
    document = (
        f"Incident ID: {incident_id}\n"
        f"Date: {now.isoformat().replace('+00:00', 'Z')}\n"
        f"Service: {service}\n"
        f"Severity: {severity}\n"
        f"Title: {title}\n"
        f"Symptoms: Reported through the Close the loop form by {resolver}.\n"
        f"Root cause: {root_cause}\n"
        f"Resolution:\n1. {fixed_one_line}\n"
        f"What failed (made it worse):\n{failed_block}\n"
        f"TTR: {ttr_minutes} minutes\n"
        f"Responder: {resolver}"
    )
    return incident_id, document


_ID_RE = re.compile(r"\bINC-[A-Z0-9-]+\b")
_SOURCE_RE = re.compile(r"\b(?:INC|POL)-[A-Z0-9-]+\b")


def _cited_ids(markdown: str) -> set[str]:
    """Incident IDs the briefing actually cites."""
    return set(_ID_RE.findall(markdown))


def _pitfall_count(markdown: str) -> int:
    """Bullets under **Do NOT do**, ignoring the no-evidence placeholder."""
    block = re.search(
        r"\*\*Do NOT do\*\*\s*\n(.*?)(?=\n\*\*|\Z)", markdown, re.DOTALL
    )
    if not block:
        return 0
    return sum(
        1
        for line in block.group(1).splitlines()
        if line.strip().startswith("- ") and "No documented" not in line
    )


# ---------------------------------------------------------------- UI helpers
def _sections(markdown: str) -> dict[str, str]:
    """Split the agent's five-section briefing without changing it."""
    text = markdown.split("\n---\n")[0]
    matches = list(re.finditer(r"^\*\*(.+?)\*\*\s*$", text, re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if title.startswith("Likely root cause"):
            sections["root"] = body
        elif title.startswith("Matching past incidents"):
            sections["match"] = body
        elif title.startswith("Do first"):
            sections["do"] = body
        elif title.startswith("Do NOT do"):
            sections["avoid"] = body
        elif title.startswith("Escalate"):
            sections["escalate"] = body
    return sections


def _confidence(markdown: str) -> str:
    match = re.search(r"Likely root cause\s*[—–-]\s*(high|medium|low)", markdown, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _bullets(block: str) -> list[str]:
    items: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^\s*[-*]\s+(.+)$", line)
        if match:
            items.append(match.group(1).strip())
    return items


def _numbered(block: str) -> list[str]:
    items: list[str] = []
    for line in block.splitlines():
        match = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if match:
            items.append(match.group(1).strip())
    if not items:
        items = _bullets(block)
    return items


def _plain(text: str) -> str:
    return re.sub(r"[*_`]+", "", text).strip()


def _commands(text: str) -> list[str]:
    return [command.strip() for command in re.findall(r"`([^`]+)`", text) if command.strip()]


def _without_commands(text: str) -> str:
    cleaned = re.sub(r"`[^`]+`", "", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -—:")
    return cleaned


def _memory_meta(memory: Memory) -> dict[str, Any]:
    """Presentation-only parse of one recalled memory."""
    incident = parse_incident(memory.text)
    if incident:
        return {
            "kind": "incident",
            "id": incident.id,
            "service": incident.service,
            "title": incident.title,
            "date": incident.date,
            "root_cause": incident.root_cause,
            "steps": incident.steps,
            "failed": incident.what_failed,
            "ttr": incident.ttr_minutes,
            "responder": incident.responder,
            "score": memory.score,
        }
    policy_id = re.search(r"Policy ID:\s*(\S+)", memory.text)
    policy_text = re.search(r"Team policy:\s*(.+)", memory.text)
    if policy_id:
        return {
            "kind": "policy",
            "id": policy_id.group(1),
            "title": "Team policy",
            "text": policy_text.group(1).strip() if policy_text else memory.text,
            "score": memory.score,
        }
    return {"kind": "note", "id": "", "title": "Recalled context", "text": memory.text, "score": memory.score}


def _section_head(title: str, subtitle: str = "", right: str = "") -> str:
    sub = f'<div class="section-sub">{esc(subtitle)}</div>' if subtitle else ""
    return (
        f'<div class="section-head"><div><div class="section-title">{esc(title)}</div>{sub}</div>'
        f"<div>{right}</div></div>"
    )


def friendly_error(title: str, message: str, *, key: str) -> None:
    """A friendly error card; never a raw traceback."""
    st.markdown(
        f'<div class="error-card"><div class="error-title">⚠ {esc(title)}</div>'
        f'<div class="error-body">{esc(message)}</div></div>',
        unsafe_allow_html=True,
    )


def _time_saved(result: dict[str, Any]) -> str:
    memories = len(result.get("memories") or [])
    if not memories:
        return "—"
    pitfalls = _pitfall_count(result.get("with", ""))
    new_ids = _cited_ids(result.get("with", "")) - _cited_ids(result.get("without", ""))
    minutes = min(45, 5 + 4 * pitfalls + 2 * len(new_ids))
    return f"~{minutes} min"


def _render_impact_strip(result: dict[str, Any]) -> None:
    without_ids = _cited_ids(result["without"])
    with_ids = _cited_ids(result["with"])
    pitfalls_before = _pitfall_count(result["without"])
    pitfalls_after = _pitfall_count(result["with"])
    memories = len(result["memories"])
    with st.container(border=True, key="impact_strip"):
        st.markdown(
            f"""
            <div class="impact-grid">
              <div class="impact-item">
                <div class="impact-value">{len(without_ids)} → {len(with_ids)}</div>
                <div class="impact-label">Incident IDs cited</div>
              </div>
              <div class="impact-item">
                <div class="impact-value">{pitfalls_before} → {pitfalls_after}</div>
                <div class="impact-label">Pitfalls caught</div>
              </div>
              <div class="impact-item">
                <div class="impact-value">{memories}</div>
                <div class="impact-label">Memories recalled</div>
              </div>
              <div class="impact-item">
                <div class="impact-value">{_time_saved(result)}</div>
                <div class="impact-label">Est. time saved</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_avoid(markdown: str) -> None:
    items = [item for item in _bullets(_sections(markdown).get("avoid", "")) if "No documented" not in item]
    st.markdown(
        '<div class="avoid-head"><span class="title">⛔ Avoid this</span>'
        f'{chip("Negative memory", "red", "🧠")}</div>',
        unsafe_allow_html=True,
    )
    if not items:
        st.markdown(
            '<div class="avoid-empty">✅ No documented harmful actions for this pattern. '
            "Proceed carefully and retain the outcome.</div>",
            unsafe_allow_html=True,
        )
        return
    for item in items:
        incident = re.search(r"\bINC-[A-Z0-9-]+\b", item)
        body = re.sub(r"^\**INC-[A-Z0-9-]+\**[:\s-]*", "", item)
        body = _plain(body)
        badge = chip(incident.group(0), "red") if incident else ""
        st.markdown(
            f'<div class="avoid-card"><span class="avoid-icon">⛔</span>'
            f'<div>{badge} {esc(body)}</div></div>',
            unsafe_allow_html=True,
        )


def _render_structured(markdown: str, *, include_avoid: bool = False) -> None:
    """Render the briefing as scannable cards instead of a Markdown wall."""
    sections = _sections(markdown)
    if not sections:
        st.markdown(markdown)
        return

    if include_avoid and "avoid" in sections:
        _render_avoid(markdown)

    if "root" in sections:
        confidence = _confidence(markdown)
        tone = {"high": "green", "medium": "amber", "low": "blue"}.get(confidence, "")
        badge = chip(f"{confidence} confidence", tone, "🎯") if confidence else ""
        st.markdown(f'<div class="mini-head">🎯 Likely root cause {badge}</div>', unsafe_allow_html=True)
        st.markdown(sections["root"])

    if "do" in sections:
        steps = _numbered(sections["do"])
        st.markdown('<div class="mini-head">🚑 Do first</div>', unsafe_allow_html=True)
        for index, step in enumerate(steps, 1):
            commands = _commands(step)
            text = _without_commands(step)
            st.markdown(
                f'<div class="step-line"><span class="step-num">{index}</span>'
                f"<span>{esc(_plain(text)) if text else 'Run the command below.'}</span></div>",
                unsafe_allow_html=True,
            )
            for command in commands:
                st.code(command, language="bash")
        if any(_commands(step) for step in steps):
            st.markdown(
                f'<div class="chip-row">{chip("Requires human approval before running", "amber", "⚠")}</div>',
                unsafe_allow_html=True,
            )

    if "match" in sections:
        rows = []
        for item in _bullets(sections["match"]):
            match = re.match(r"\*\*(INC-[A-Z0-9-]+)\*\*\s*(.*)", item)
            if match:
                rows.append((match.group(1), _plain(match.group(2))))
            else:
                rows.append(("", _plain(item)))
        st.markdown('<div class="mini-head">🗂 Matching past incidents</div>', unsafe_allow_html=True)
        if rows:
            for incident_id, text in rows:
                badge = chip(incident_id, "blue", "📌") if incident_id else ""
                st.markdown(
                    f'<div class="incident-row">{badge}<span>{esc(text)}</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="muted">None in memory.</div>', unsafe_allow_html=True)

    if "escalate" in sections:
        items = _bullets(sections["escalate"])
        if items:
            list_items = "".join(f"<li>{esc(_plain(item))}</li>" for item in items)
            st.markdown(
                '<div class="escalate-card"><div class="mini-head">☎ Escalate</div>'
                f"<ul>{list_items}</ul></div>",
                unsafe_allow_html=True,
            )


def _render_recalled(memories: list[Memory]) -> None:
    st.markdown(
        _section_head(
            "Recalled memories",
            "Every card below came from Hindsight recall — nothing is invented.",
            chip(f"{len(memories)} recalled", "indigo", "🗂"),
        ),
        unsafe_allow_html=True,
    )
    if not memories:
        st.caption("No memories were recalled for this alert.")
        return
    for memory in memories:
        meta = _memory_meta(memory)
        score = meta.get("score") or 0.0
        if meta["kind"] == "incident":
            label = f"📌 {meta['id']} · {meta['service'] or 'service'} · match {score:.2f}"
        elif meta["kind"] == "policy":
            label = f"📘 {meta['id']} · team policy · match {score:.2f}"
        else:
            label = f"🗂 Recalled context · match {score:.2f}"
        with st.expander(label):
            badges = []
            if meta["kind"] == "incident":
                if meta["failed"]:
                    badges.append(chip(f"Made it worse ({len(meta['failed'])})", "red", "⛔"))
                if meta["steps"]:
                    badges.append(chip("Worked before", "green", "✅"))
                if meta["ttr"]:
                    badges.append(chip(f"TTR {meta['ttr']} min", "blue", "⏱"))
                if meta["responder"]:
                    badges.append(chip(meta["responder"], "", "👤"))
            st.markdown(f'<div class="chip-row">{"".join(badges)}</div>', unsafe_allow_html=True)

            if meta["kind"] == "incident":
                st.markdown(f"**{esc(meta['title'])}**")
                if meta["date"]:
                    st.caption(f"Incident date {meta['date']}")
                if meta["root_cause"]:
                    st.markdown(f"**Root cause** — {esc(meta['root_cause'])}")
                if meta["steps"]:
                    st.markdown("**What worked**")
                    for step in meta["steps"]:
                        st.markdown(f"- {step}")
                if meta["failed"]:
                    st.markdown("**What made it worse**")
                    for item in meta["failed"]:
                        st.markdown(
                            f'<div class="avoid-card"><span class="avoid-icon">⛔</span>'
                            f"<div>{esc(item)}</div></div>",
                            unsafe_allow_html=True,
                        )
            elif meta["kind"] == "policy":
                st.markdown(f"**{esc(meta['title'])}**")
                st.markdown(meta["text"])
            else:
                st.markdown(meta["text"])


def _seed(store: MemoryStore) -> None:
    if store.backend != "hindsight":
        st.session_state["seed_errors"] = [
            "Hindsight is unavailable, so nothing can be retained. Start the server and retry the connection."
        ]
        st.rerun()
    status = st.status("Seeding incident memory…", expanded=True)
    progress = st.progress(0.0, text="Preparing 11 incidents and 4 policies…")
    with st.spinner("Retaining 11 incidents and 4 policies in Hindsight…"):
        _ensure_connected(store)
        stored, incident_count, errors = seed_memories(store, progress)
    if errors:
        status.update(label=f"Seeded {stored} documents with {len(errors)} error(s)", state="error")
        st.session_state["seed_errors"] = errors
        st.session_state["seed_toast"] = None
    else:
        status.update(label=f"Seeded {stored} memories", state="complete")
        st.session_state["seed_errors"] = []
        st.session_state["seed_toast"] = f"Seeded {stored} memories — memory is live."
    st.session_state["seeded_docs"] = stored
    st.session_state["seeded_incidents"] = incident_count
    st.session_state["bank_probe"] = False
    st.rerun()


def _bank_is_empty(store: MemoryStore) -> bool:
    if not store.connected:
        return False
    if "bank_probe" in st.session_state:
        return bool(st.session_state["bank_probe"])
    try:
        hits = store.recall("incident", limit=1)
        st.session_state["bank_probe"] = len(hits) == 0
    except Exception as exc:
        message = str(exc).lower()
        st.session_state["bank_probe"] = "not found" in message or "404" in message
    return bool(st.session_state["bank_probe"])


def _ensure_connected(store: MemoryStore) -> None:
    """Rebind the Hindsight client to the current Streamlit run.

    Streamlit executes every rerun in a fresh thread/event loop. The Hindsight
    sync wrappers bind their HTTP client to the loop they first ran in, so a
    cached store raises ``Event loop is closed`` on the next interaction. A
    reconnect inside the run that is about to use memory is cheap and keeps the
    store honest: if Hindsight is down, the operation still fails loudly.
    """
    store.connect()


def _execute_briefing(store: MemoryStore, service: str, alert: str, logs: str) -> None:
    st.session_state["last_request"] = {"service": service, "alert": alert, "logs": logs}
    try:
        with st.spinner("Recalling similar incidents from Hindsight…"):
            _ensure_connected(store)
            without_memory, _ = run_agent(service, alert, logs, store, use_memory=False)
            with_memory, memories = run_agent(service, alert, logs, store, use_memory=True)
        st.session_state["last_result"] = {
            "service": service,
            "alert": alert,
            "without": without_memory,
            "with": with_memory,
            "memories": memories,
            "backend": store.backend,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        }
        st.session_state["briefing_error"] = None
    except Exception as exc:
        st.session_state["briefing_error"] = {
            "title": "Could not build a memory-grounded briefing",
            "message": (
                f"{type(exc).__name__}: {exc}. The app will not fake memory; "
                "check the Hindsight connection and retry."
            ),
        }


def _nav_to(label: str) -> None:
    st.session_state["nav"] = label
    st.query_params["tab"] = NAV_SLUG[label]


def _load_sample_payload() -> None:
    st.session_state["ou_raw"] = json.dumps(SAMPLE_PAYLOAD, indent=2)
    st.session_state["ou_error"] = None


def _reset_intake() -> None:
    st.session_state.pop("ou_parsed", None)
    st.session_state.pop("ou_retained", None)
    st.session_state.pop("ou_raw", None)
    st.session_state.pop("ou_error", None)


def _try_chaos(action: str) -> None:
    """If the real checkout-api microservice is running on :8080, trigger chaos/recovery."""
    try:
        req = urllib.request.Request(f"http://localhost:8080/chaos/{action}", method="POST")
        urllib.request.urlopen(req, timeout=0.8)
    except Exception:
        pass


# ---------------------------------------------------------------- store + sidebar
store = get_store()
seeded_docs = st.session_state.get("seeded_docs", 0)
seeded_incidents = st.session_state.get("seeded_incidents", 0)
seeded_policies = len(POLICIES) if seeded_docs else 0
seeded_memories = seeded_docs
bank_empty = _bank_is_empty(store)
if seeded_docs:
    counter_incidents, counter_policies, counter_memories = (
        seeded_incidents,
        seeded_policies,
        seeded_memories,
    )
elif bank_empty:
    counter_incidents, counter_policies, counter_memories = 0, 0, 0
else:
    counter_incidents = counter_policies = counter_memories = "—"

with st.sidebar:
    st.markdown(
        '<div class="brand">RecallOps</div>'
        '<div class="brand-sub">Northwind Pay</div>',
        unsafe_allow_html=True,
    )

    if store.backend == "hindsight":
        st.markdown(
            f"""
            <div class="status-card">
              <div class="status-row"><span class="dot green"></span>Hindsight connected</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="status-card">
              <div class="status-row"><span class="dot red"></span>Hindsight unavailable</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if store.error:
            with st.expander("Connection details"):
                st.code(store.error, language="text")
        if st.button("Retry Hindsight connection", use_container_width=True):
            load_dotenv(override=True)
            _load_streamlit_secrets()
            st.cache_resource.clear()
            store.connect()
            st.session_state.pop("bank_probe", None)
            st.rerun()

    seed_errors = st.session_state.get("seed_errors") or []
    if seed_errors:
        friendly_error(
            f"{len(seed_errors)} document(s) failed to seed",
            seed_errors[0] + (" …" if len(seed_errors) > 1 else ""),
            key="seed_error",
        )

    if seeded_docs:
        st.markdown(
            f'<div class="success-card">✅ {seeded_docs} memories retained this session</div>',
            unsafe_allow_html=True,
        )
        if st.button("Re-seed memory", use_container_width=True):
            _seed(store)
    else:
        if st.button(
            "Seed 11 incidents + 4 policies",
            use_container_width=True,
            type="primary",
            disabled=store.backend != "hindsight",
        ):
            _seed(store)
        if store.backend != "hindsight":
            st.caption("Connect to Hindsight before seeding.")

    st.markdown(
        f"""
        <div class="metric-grid">
          <div class="metric-card"><span class="metric-value">{counter_incidents}</span><span class="metric-label">Incidents</span></div>
          <div class="metric-card"><span class="metric-value">{counter_policies}</span><span class="metric-label">Policies</span></div>
          <div class="metric-card"><span class="metric-value">{counter_memories}</span><span class="metric-label">Memories</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

toast_message = st.session_state.pop("seed_toast", None)
if toast_message:
    st.toast(toast_message, icon="✅")

# ---------------------------------------------------------------- header + nav
st.markdown(
    """
    <h1 class="page-title">Incident memory</h1>
    """,
    unsafe_allow_html=True,
)

query_tab = st.query_params.get("tab")
if isinstance(query_tab, list):
    query_tab = query_tab[0] if query_tab else None
if "nav" not in st.session_state:
    st.session_state["nav"] = SLUG_LABEL.get(str(query_tab or ""), "Briefing")

active_tab = st.segmented_control(
    "Primary navigation",
    NAV_LABELS,
    key="nav",
    label_visibility="collapsed",
    on_change=lambda: st.query_params.update(
        {"tab": NAV_SLUG.get(st.session_state.get("nav", "Briefing"), "briefing")}
    ),
)
if not active_tab:
    active_tab = st.session_state.get("nav", "Briefing")

# ---------------------------------------------------------------- briefing
if active_tab == "Briefing":
    result = st.session_state.get("last_result")
    prefill = st.session_state.get("briefing_prefill")
    briefing_error = st.session_state.get("briefing_error")

    if store.backend != "hindsight":
        with st.container(border=True, key="hero_card"):
            st.markdown(
                """
                <div class="hero-title">Memory is offline</div>
                <p class="hero-body">Connect to Hindsight to access incident history.</p>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Retry Hindsight connection", type="primary", key="hero_retry"):
                store.connect()
                st.session_state.pop("bank_probe", None)
                st.rerun()
    elif bank_empty and not seeded_docs:
        with st.container(border=True, key="hero_card"):
            st.markdown(
                f"""
                <div class="hero-title">No memory yet</div>
                <p class="hero-body">Add 11 sample incidents and 4 policies to get started.</p>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Seed 11 incidents + 4 policies", type="primary", key="hero_seed"):
                _seed(store)
    elif not result and not briefing_error:
        st.markdown(
            f"""
            <div class="ready-strip">
              {chip("Memory ready", "green", "✅")}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if prefill:
        st.markdown(
            f'<div class="ready-strip">{chip("New memory retained", "green", "✅")}'
            f'<span>{esc(prefill.get("service", "service"))} · {esc(prefill.get("alert", "alert"))}</span>'
            '<span class="muted">Run the briefing to see it recalled.</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        _section_head(
            "Choose an alert",
        ),
        unsafe_allow_html=True,
    )

    preset_columns = st.columns(len(DEMO_ALERTS), gap="small")
    for index, (name, preset) in enumerate(DEMO_ALERTS.items()):
        service, title, blurb, severity = PRESET_META.get(name, (preset["service"], name, "", ""))
        with preset_columns[index]:
            with st.container(border=True, key=f"preset_{index}"):
                st.markdown(
                    f'<div class="chip-row">{chip(service, "blue")}{chip(severity, "amber")}</div>'
                    f'<div class="preset-title">{esc(title)}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Run briefing →", key=f"run_preset_{index}", use_container_width=True):
                    _execute_briefing(store, preset["service"], preset["alert"], preset["logs"])

    with st.expander("Custom alert", expanded=False):
        st.session_state.setdefault("custom_service", "checkout-api")
        st.session_state.setdefault("custom_alert", "Checkout API 5xx rate 18% for 8 minutes")
        st.session_state.setdefault("custom_logs", "")
        if prefill:
            st.session_state["custom_service"] = prefill.get("service", st.session_state["custom_service"])
            st.session_state["custom_alert"] = prefill.get("alert", st.session_state["custom_alert"])
        with st.form("custom_briefing"):
            col_service, col_alert = st.columns([1, 2])
            with col_service:
                st.text_input("Service", key="custom_service")
            with col_alert:
                st.text_input("Alert", key="custom_alert")
            st.text_area("Logs", key="custom_logs", height=150, placeholder="Paste the log excerpt or symptoms…")
            custom_run = st.form_submit_button("Run incident briefing", type="primary")
        if custom_run:
            service = st.session_state["custom_service"].strip()
            alert = st.session_state["custom_alert"].strip()
            if not service or not alert:
                st.session_state["briefing_error"] = {
                    "title": "Service and alert are required",
                    "message": "Add a service name and a one-line alert before running the briefing.",
                }
            else:
                _execute_briefing(store, service, alert, st.session_state["custom_logs"])

    if briefing_error:
        friendly_error(briefing_error["title"], briefing_error["message"], key="briefing_error")
        if st.button("Retry briefing", key="retry_briefing", type="primary"):
            request = st.session_state.get("last_request") or {}
            if request:
                _execute_briefing(store, request["service"], request["alert"], request["logs"])

    result = st.session_state.get("last_result")
    if result:
        st.markdown(
            _section_head(
                "Briefing",
                f"{result['service']} · ran {result['at']} · backend {result['backend']} · "
                f"{len(result['memories'])} memories recalled",
                chip("Grounded in Hindsight", "green", "✅"),
            ),
            unsafe_allow_html=True,
        )
        _render_impact_strip(result)
        _render_avoid(result["with"])

        col_without, col_with = st.columns(2, gap="large")
        with col_without:
            with st.container(border=True, key="without_card"):
                st.markdown(
                    f'<div class="mini-head">Without memory {chip("Generic runbook", "red", "⚠")}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(result["without"])
        with col_with:
            with st.container(border=True, key="with_card"):
                st.markdown(
                    f'<div class="mini-head">With Hindsight memory {chip("Cited + grounded", "green", "✅")}</div>',
                    unsafe_allow_html=True,
                )
                _render_structured(result["with"])

        _render_recalled(result["memories"])

# ---------------------------------------------------------------- service monitor
elif active_tab == "Service monitor":
    st.markdown(
        _section_head(
            "Service monitor",
            "Monitor health and investigate outages.",
        ),
        unsafe_allow_html=True,
    )

    active_outage: OneUptimeIncident | None = st.session_state.get("active_outage")

    def get_svc_state(svc_name: str, default_p95: str) -> tuple[str, str]:
        if active_outage and active_outage.service == svc_name:
            return "Outage", "5xx spike"
        return "Operational", f"p95 {default_p95}"

    services = [
        ("checkout-api", "185ms"),
        ("payment-gateway", "320ms"),
        ("auth-service", "42ms"),
        ("orders-db", "12ms"),
    ]
    service_columns = st.columns(4, gap="small")
    for column, (service_name, p95) in zip(service_columns, services):
        status, detail = get_svc_state(service_name, p95)
        tone = "red" if status == "Outage" else "green"
        icon = "🔴" if status == "Outage" else "🟢"
        with column:
            with st.container(border=True):
                st.markdown(
                    f'<div class="chip-row">{chip(status, tone, icon)}</div>'
                    f'<div class="preset-title">{esc(service_name)}</div>'
                    f'<div class="preset-blurb">{esc(detail)}</div>',
                    unsafe_allow_html=True,
                )

    col_break, col_probe = st.columns(2, gap="large")

    with col_break:
        with st.container(border=True):
            st.markdown('<div class="mini-head">💥 Break a service</div>', unsafe_allow_html=True)
            st.caption("Trigger an outage to see OneUptime open an incident.")
            scenario_keys = list(SIMULATED_SCENARIOS.keys())
            scenario_labels = {
                "checkout-pool-exhaustion": "checkout-api: Pool exhaustion after v3.4.1 (502/504)",
                "payment-gateway-timeout": "payment-gateway: Acquirer timeout, circuit breaker (504)",
                "auth-cache-eviction": "auth-service: Redis token cache eviction storm (500)",
                "orders-db-disk-pressure": "orders-db: Postgres IOPS saturation, pool full",
            }
            chosen_scenario = st.selectbox(
                "Outage scenario",
                scenario_keys,
                format_func=lambda key: scenario_labels.get(key, key),
                key="monitor_scenario_select",
            )
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("💥 Break service", type="primary", use_container_width=True, key="btn_trigger_outage"):
                    if chosen_scenario == "checkout-pool-exhaustion":
                        _try_chaos("break")
                    st.session_state["active_outage"] = create_incident_from_scenario(chosen_scenario)
                    st.session_state["outage_briefing"] = None
                    st.rerun()
            with col_b2:
                if st.button("🔄 Recover all", use_container_width=True, key="btn_recover_services"):
                    _try_chaos("heal")
                    st.session_state["active_outage"] = None
                    st.session_state["outage_briefing"] = None
                    st.rerun()

    with col_probe:
        with st.container(border=True):
            st.markdown('<div class="mini-head">🔌 Probe a URL</div>', unsafe_allow_html=True)
            st.caption("Run a synthetic HTTP check against anything, including localhost.")
            col_preset1, col_preset2 = st.columns(2)
            with col_preset1:
                if st.button("📦 Local checkout-api (:8080)", use_container_width=True, key="btn_preset_local"):
                    st.session_state["monitor_probe_url"] = "http://localhost:8080/health"
                    st.session_state["monitor_probe_svc"] = "checkout-api"
                    st.rerun()
            with col_preset2:
                if st.button("🌐 Public httpbin", use_container_width=True, key="btn_preset_httpbin"):
                    st.session_state["monitor_probe_url"] = "https://httpbin.org/status/200"
                    st.session_state["monitor_probe_svc"] = "public-api"
                    st.rerun()

            default_url = st.session_state.get("monitor_probe_url", "http://localhost:8080/health")
            default_svc = st.session_state.get("monitor_probe_svc", "checkout-api")
            probe_url = st.text_input(
                "Target URL",
                value=default_url,
                placeholder="https://api.yourcompany.com/health",
                key="monitor_probe_url_input",
            )
            probe_svc = st.text_input("Service label", value=default_svc, key="monitor_probe_svc_input")
            if st.button("⚡ Probe endpoint now", use_container_width=True, key="btn_probe_now"):
                with st.spinner(f"Probing {probe_url}…"):
                    st.session_state["last_probe"] = probe_endpoint(probe_url, timeout=4.0, service=probe_svc)

            last_probe: ProbeResult | None = st.session_state.get("last_probe")
            if last_probe:
                if last_probe.healthy:
                    st.markdown(
                        f'<div class="success-card">🟢 HTTP {last_probe.status_code} · {last_probe.latency_ms} ms</div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(last_probe.url)
                else:
                    st.markdown(
                        f'<div class="error-card"><div class="error-title">🔴 HTTP {last_probe.status_code}</div>'
                        f'<div class="error-body">{esc(last_probe.error)}</div></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(last_probe.url)
                    if st.button("🚨 Declare incident from probe", type="primary", key="btn_declare_probe_inc"):
                        st.session_state["active_outage"] = create_incident_from_probe(last_probe)
                        st.session_state["outage_briefing"] = None
                        st.rerun()

    if active_outage:
        st.markdown(
            f'<div class="error-card"><div class="error-title">🚨 Active incident {esc(active_outage.id)}</div>'
            f'<div class="error-body">{esc(active_outage.title)}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="chip-row">{chip(active_outage.service, "blue", "🛰")}'
            f'{chip(active_outage.severity, "amber", "⚠")}{chip(active_outage.status, "red", "🚨")}</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Telemetry & error logs", expanded=True):
            st.code(active_outage.symptoms, language="text")

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            run_copilot = st.button(
                "🧠 Investigate with memory", type="primary", use_container_width=True, key="btn_copilot_investigate"
            )
        with col_act2:
            resolve_now = st.button(
                "✅ Resolve & retain post-mortem", use_container_width=True, key="btn_resolve_outage"
            )

        if run_copilot:
            try:
                with st.spinner("OneUptime alert dispatched. Recalling similar incidents…"):
                    _ensure_connected(store)
                    without_outage, _ = run_agent(
                        active_outage.service, active_outage.title, active_outage.symptoms, store, use_memory=False
                    )
                    with_outage, outage_memories = run_agent(
                        active_outage.service, active_outage.title, active_outage.symptoms, store, use_memory=True
                    )
                st.session_state["outage_briefing"] = {
                    "without": without_outage,
                    "with": with_outage,
                    "memories": outage_memories,
                }
            except Exception as exc:
                st.session_state["outage_briefing"] = None
                friendly_error(
                    "Could not investigate this incident",
                    f"{type(exc).__name__}: {exc}",
                    key="outage_error",
                )

        outage_briefing = st.session_state.get("outage_briefing")
        if outage_briefing:
            st.markdown('<div class="mini-head">Incident briefing</div>', unsafe_allow_html=True)
            _render_impact_strip(
                {
                    **outage_briefing,
                    "service": active_outage.service,
                    "at": "now",
                    "backend": store.backend,
                }
            )
            _render_avoid(outage_briefing["with"])
            col_b_without, col_b_with = st.columns(2, gap="large")
            with col_b_without:
                with st.container(border=True, key="without_card"):
                    st.markdown(f'<div class="mini-head">Without memory {chip("Generic runbook", "red", "⚠")}</div>', unsafe_allow_html=True)
                    st.markdown(outage_briefing["without"])
            with col_b_with:
                with st.container(border=True, key="with_card"):
                    recalled_chip = chip(f"{len(outage_briefing['memories'])} recalled", "green", "✅")
                    st.markdown(
                        f'<div class="mini-head">With memory {recalled_chip}</div>',
                        unsafe_allow_html=True,
                    )
                    _render_structured(outage_briefing["with"])

            _render_recalled(outage_briefing["memories"])

        if resolve_now:
            try:
                _ensure_connected(store)
                _try_chaos("heal")
                store.retain(
                    oneuptime_to_document(active_outage),
                    context=f"OneUptime incident {active_outage.id} resolved on {active_outage.service}",
                    timestamp=active_outage.date,
                    document_id=f"oneuptime-{active_outage.id}",
                    update_mode="replace",
                )
                st.session_state["active_outage"] = None
                st.session_state["outage_briefing"] = None
                st.session_state["close_toast"] = f"Incident {active_outage.id} resolved and retained."
                st.rerun()
            except Exception as exc:
                friendly_error(
                    "Could not retain the resolution",
                    f"{type(exc).__name__}: {exc}",
                    key="resolve_error",
                )

# ---------------------------------------------------------------- OneUptime intake
elif active_tab == "OneUptime intake":
    parsed = st.session_state.get("ou_parsed")
    retained = st.session_state.get("ou_retained")
    active_step = 3 if retained else (2 if parsed else 1)

    st.markdown(
        _section_head(
            "OneUptime intake",
            "Import an incident into memory.",
        ),
        unsafe_allow_html=True,
    )

    step_html = "".join(
        f'<div class="step-pill {"active" if number == active_step else "done" if number < active_step else ""}">'
        f'<span class="n">{"✓" if number < active_step else number}</span>{esc(label)}</div>'
        for number, label in ((1, "Paste"), (2, "Review"), (3, "Retain"))
    )
    st.markdown(f'<div class="stepper">{step_html}</div>', unsafe_allow_html=True)

    if retained:
        st.markdown(
            f'<div class="success-card">✅ Retained <strong>{esc(retained["id"])}</strong> — '
            f'{esc(retained["service"])}: {esc(retained["title"])}. A future alert can now cite it.</div>',
            unsafe_allow_html=True,
        )
        col_after_1, col_after_2 = st.columns(2)
        with col_after_1:
            if st.button("View it in the Briefing", type="primary", use_container_width=True, key="ou_view_briefing"):
                st.session_state["briefing_prefill"] = {
                    "service": retained["service"],
                    "alert": retained["title"],
                }
                _nav_to("Briefing")
                st.rerun()
        with col_after_2:
            st.button("Start a new intake", use_container_width=True, key="ou_new", on_click=_reset_intake)
        st.divider()

    col_paste, col_sample = st.columns([3, 2], gap="large")
    with col_paste:
        st.markdown('<div class="mini-head">1 · Paste a OneUptime payload</div>', unsafe_allow_html=True)
        raw = st.text_area(
            "OneUptime incident JSON or text",
            key="ou_raw",
            height=220,
            placeholder=(
                '{"title": "Checkout 5xx", "service": "checkout-api", '
                '"rootCause": "...", "resolution": "..."}'
            ),
        )
        st.markdown(
            f'<div class="hint-row">Plain text also works: {chip("Title:", "")}{chip("Service:", "")}'
            f'{chip("Root cause:", "")}{chip("Resolution:", "")}</div>',
            unsafe_allow_html=True,
        )
        if st.button("Parse incident", type="primary", key="ou_parse"):
            try:
                st.session_state["ou_parsed"] = parse_oneuptime(raw)
                st.session_state["ou_retained"] = None
                st.session_state["ou_error"] = None
                st.rerun()
            except Exception as exc:
                st.session_state["ou_error"] = f"{type(exc).__name__}: {exc}"

    with col_sample:
        sample = {
            "number": 9001,
            "title": "Checkout 5xx after v3.4.1",
            "service": "checkout-api",
            "severity": "Critical",
            "rootCause": "Pool exhausted by a blocking FX call.",
            "resolution": "Rollback to v3.4.0.",
            "whatFailed": "Scaling and restarting made it worse.",
        }
        with st.container(border=True, key="sample_card"):
            st.markdown('<div class="mini-head">Styled sample payload</div>', unsafe_allow_html=True)
            st.caption("A realistic OneUptime Workflows payload. Load it, then edit any field.")
            st.code(json.dumps(sample, indent=2), language="json", height=300)
            st.button(
                "Load sample payload",
                use_container_width=True,
                key="ou_load_sample",
                on_click=_load_sample_payload,
            )

    if st.session_state.get("ou_error"):
        friendly_error("Could not parse that payload", st.session_state["ou_error"], key="ou_parse_error")

    parsed = st.session_state.get("ou_parsed")
    if parsed:
        st.markdown('<div class="mini-head">2 · Review parsed fields</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="chip-row">{chip(parsed.id, "blue", "📌")}{chip(parsed.service, "", "🛰")}'
            f'{chip(parsed.severity or "severity unknown", "amber", "⚠")}'
            f'{chip(parsed.status or "status unknown", "", "📋")}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Normalized ID {parsed.id} · OneUptime ID {parsed.oneuptime_id or 'unknown'}")
        with st.form(f"oneuptime_form_{parsed.id}"):
            field_left, field_right = st.columns(2)
            with field_left:
                ou_title = st.text_input("Title *", value=parsed.title, key=f"ou_title_{parsed.id}")
                ou_service = st.text_input("Service *", value=parsed.service, key=f"ou_service_{parsed.id}")
                severity_options = ["Critical", "High", "Medium", "Low", "Unknown"]
                severity_index = severity_options.index(parsed.severity) if parsed.severity in severity_options else 4
                ou_severity = st.selectbox(
                    "Severity", severity_options, index=severity_index, key=f"ou_severity_{parsed.id}"
                )
                ou_status = st.text_input("Status", value=parsed.status, key=f"ou_status_{parsed.id}")
            with field_right:
                ou_ttr = st.number_input(
                    "TTR (minutes)",
                    min_value=0,
                    max_value=100000,
                    value=int(parsed.ttr_minutes),
                    step=1,
                    key=f"ou_ttr_{parsed.id}",
                )
                ou_responder = st.text_input("Responder", value=parsed.responder, key=f"ou_responder_{parsed.id}")
                ou_url = st.text_input("OneUptime URL", value=parsed.url, key=f"ou_url_{parsed.id}")
            ou_root = st.text_area("Root cause *", value=parsed.root_cause, height=80, key=f"ou_root_{parsed.id}")
            ou_resolution = st.text_area(
                "Resolution / remediation *", value=parsed.resolution, height=100, key=f"ou_resolution_{parsed.id}"
            )
            ou_failed = st.text_area(
                "What failed (made it worse) ⛔",
                value=parsed.what_failed,
                height=80,
                key=f"ou_failed_{parsed.id}",
                help="Negative memory: actions that worsened the incident and should be avoided in future runs.",
            )
            ou_symptoms = st.text_area(
                "Symptoms / logs", value=parsed.symptoms, height=150, key=f"ou_symptoms_{parsed.id}"
            )
            run_after = st.checkbox(
                "Run a before/after briefing after retaining",
                value=True,
                key=f"ou_run_after_{parsed.id}",
            )
            submitted = st.form_submit_button("🔁 3 · Retain in Hindsight", type="primary")

        if submitted:
            missing = [
                label
                for label, value in (
                    ("Title", ou_title),
                    ("Service", ou_service),
                    ("Root cause", ou_root),
                    ("Resolution", ou_resolution),
                )
                if not value.strip()
            ]
            if missing:
                friendly_error(
                    "Some required fields are missing",
                    "Add the following before retaining: " + ", ".join(missing) + ".",
                    key="ou_validation",
                )
            else:
                final = replace(
                    parsed,
                    title=ou_title.strip(),
                    service=ou_service.strip(),
                    severity=ou_severity.strip(),
                    status=ou_status.strip(),
                    root_cause=ou_root.strip(),
                    resolution=ou_resolution.strip(),
                    what_failed=ou_failed.strip(),
                    symptoms=ou_symptoms.strip(),
                    ttr_minutes=int(ou_ttr),
                    responder=ou_responder.strip(),
                    url=ou_url.strip(),
                )
                try:
                    _ensure_connected(store)
                    store.retain(
                        oneuptime_to_document(final),
                        context=(
                            f"OneUptime incident {final.id} "
                            f"(OneUptime ID {final.oneuptime_id or 'unknown'}) on {final.service}"
                        ),
                        timestamp=final.date,
                        document_id=f"oneuptime-{final.id}",
                        update_mode="replace",
                    )
                    learned = st.session_state.setdefault("learned", [])
                    learned.append(f"{final.id} — {final.service}: {final.title}")
                    st.session_state["ou_retained"] = {
                        "id": final.id,
                        "service": final.service,
                        "title": final.title,
                    }
                    st.session_state["close_toast"] = f"Retained {final.id}. Future alerts can cite it."
                    if run_after:
                        with st.spinner("Recalling the new memory for a before/after briefing…"):
                            without, _ = run_agent(
                                final.service, final.title, final.symptoms, store, use_memory=False
                            )
                            with_memory, memories = run_agent(
                                final.service, final.title, final.symptoms, store, use_memory=True
                            )
                        st.session_state["last_result"] = {
                            "service": final.service,
                            "alert": final.title,
                            "without": without,
                            "with": with_memory,
                            "memories": memories,
                            "backend": store.backend,
                            "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
                        }
                    st.rerun()
                except Exception as exc:
                    friendly_error(
                        "Could not retain the OneUptime incident",
                        f"{type(exc).__name__}: {exc}",
                        key="ou_retain_error",
                    )

    with st.expander("Receive incidents from OneUptime Workflows (webhook)"):
        st.markdown(
            "Start the receiver in a separate terminal, then use **Workflows → On Create Incident "
            "→ API Post (JSON)** in OneUptime and point it at the URL below."
        )
        st.code("uv run python src/integrations/webhook_server.py", language="bash")
        st.code(
            "curl -sS -X POST http://127.0.0.1:8787/oneuptime \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  --data @incident.json",
            language="bash",
        )
        st.markdown(
            "Accepted keys include `title`, `description`, `service`, `severity`, `status`, "
            "`rootCause`, `resolution`, `whatFailed`, `assignedTo`, `createdAt`, `resolvedAt`, "
            "`ttr`, `logs`, and `url`. Nested `incident`/`data` payloads are unwrapped."
        )
        st.caption(
            "The receiver binds to 127.0.0.1 by default and requires no token unless "
            "`ONEUPTIME_WEBHOOK_TOKEN` is set. Put it behind HTTPS and authentication before "
            "exposing it beyond your machine."
        )

# ---------------------------------------------------------------- close the loop
elif active_tab == "Close the loop":
    st.markdown(
        _section_head(
            "Close the loop",
            "Save the cause and resolution for next time.",
        ),
        unsafe_allow_html=True,
    )
    services = sorted({incident["service"] for incident in INCIDENTS})
    with st.container(border=True):
        with st.form("close_loop"):
            row_top_left, row_top_right = st.columns([1, 2])
            with row_top_left:
                close_service = st.selectbox("Service", services)
            with row_top_right:
                close_title = st.text_input("Title", placeholder="Checkout 502s after deploy v4.2.0")
            col_sev, col_ttr = st.columns(2)
            with col_sev:
                close_severity = st.selectbox("Severity", ["Sev 1 — Critical", "Sev 2 — High", "Sev 3 — Medium", "Sev 4 — Low"])
            with col_ttr:
                close_ttr = st.number_input("TTR (minutes)", min_value=1, max_value=10000, value=30)
            close_root = st.text_area("Root cause *", height=80, placeholder="What actually caused it?")
            row_mid_left, row_mid_right = st.columns(2)
            with row_mid_left:
                close_fixed = st.text_area(
                    "What fixed it *",
                    height=100,
                    placeholder="Rolled back to v4.1.9; restored pool size to 40.",
                )
            with row_mid_right:
                close_failed = st.text_area(
                    "What made it worse (Negative memory) ⛔",
                    height=100,
                    placeholder="Scaling replicas made DB connections worse; restarting pods did not help.",
                    help="Negative memory: what you record here becomes a direct warning under 'Do NOT do' in future briefings.",
                )
            close_resolver = st.text_input("Resolver *", placeholder="Your name")
            submitted = st.form_submit_button("🔁 Retain outcome in Hindsight", type="primary")

    if submitted:
        missing = [
            label
            for label, value in (
                ("Title", close_title),
                ("Root cause", close_root),
                ("What fixed it", close_fixed),
                ("Resolver", close_resolver),
            )
            if not value.strip()
        ]
        if missing:
            friendly_error(
                "Some required fields are missing",
                "Add the following before retaining: " + ", ".join(missing) + ".",
                key="close_validation",
            )
        else:
            incident_id, document = outcome_document(
                close_service,
                close_title.strip(),
                close_root.strip(),
                close_fixed.strip(),
                close_failed.strip(),
                int(close_ttr),
                close_resolver.strip(),
                close_severity.split(" — ")[0],
            )
            try:
                _ensure_connected(store)
                store.retain(
                    document,
                    context=f"just-resolved incident {incident_id} on {close_service}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                learned = st.session_state.setdefault("learned", [])
                learned.append(f"{incident_id} — {close_service}: {close_title.strip()}")
                st.session_state["close_success"] = {
                    "id": incident_id,
                    "service": close_service,
                    "title": close_title.strip(),
                }
                st.session_state["close_toast"] = f"Retained {incident_id}. The next briefing can cite it."
                st.rerun()
            except Exception as exc:
                friendly_error(
                    "Could not retain the outcome",
                    f"{type(exc).__name__}: {exc}",
                    key="close_error",
                )

    success = st.session_state.get("close_success")
    if success:
        st.markdown(
            f'<div class="success-card">✅ Retained <strong>{esc(success["id"])}</strong> — '
            f'{esc(success["service"])}: {esc(success["title"])}. Run the briefing again to see it recalled.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Run the briefing again →", type="primary", key="close_to_briefing"):
            st.session_state["briefing_prefill"] = {
                "service": success["service"],
                "alert": success["title"],
            }
            _nav_to("Briefing")
            st.rerun()

    learned_items = st.session_state.get("learned", [])
    st.markdown(
        _section_head("Learned this session", "Resolutions retained from this UI.", chip(f"{len(learned_items)}", "indigo", "📚")),
        unsafe_allow_html=True,
    )
    if not learned_items:
        st.caption("Nothing yet. Close an incident above and it appears here.")
    for item in reversed(learned_items):
        st.markdown(f'<div class="incident-row">{chip("✅", "green")}<span>{esc(item)}</span></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- reflect
elif active_tab == "Reflect":
    st.markdown(
        _section_head(
            "Ask the whole memory bank",
            "Ask about past incidents and team policies.",
        ),
        unsafe_allow_html=True,
    )

    suggested = st.pills(
        "Suggested questions",
        REFLECT_PRESETS,
        key="reflect_pills",
        label_visibility="collapsed",
    )
    custom_question = st.text_input(
        "Or ask your own question",
        key="reflect_custom",
        placeholder="e.g. Which service has the worst repeat-offender pattern?",
    )
    if st.button("🧭 Reflect across bank", type="primary", key="reflect_run"):
        question = custom_question.strip() or suggested
        if not question:
            friendly_error(
                "Pick a question first",
                "Choose a suggested question or type your own before pressing Reflect.",
                key="reflect_empty",
            )
        else:
            try:
                with st.spinner("Reflecting across the memory bank…"):
                    _ensure_connected(store)
                    answer = store.reflect(question)
                history = st.session_state.setdefault("reflect_chat", [])
                sources = sorted(set(_SOURCE_RE.findall(answer)))
                history.append(
                    {
                        "question": question,
                        "answer": answer,
                        "sources": sources,
                        "backend": store.backend,
                    }
                )
            except Exception as exc:
                friendly_error(
                    "Reflect failed",
                    f"{type(exc).__name__}: {exc}. Hindsight is required; the app will not invent an answer.",
                    key="reflect_error",
                )

    history = st.session_state.get("reflect_chat", [])
    if not history:
        st.markdown(
            f'<div class="ready-strip">{chip("Try a chip above", "indigo", "💡")}'
            '<span class="muted">Answers cite incident and policy IDs from the bank.</span></div>',
            unsafe_allow_html=True,
        )
    for turn in history:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant", avatar="🧠"):
            st.markdown(turn["answer"])
            source_chips = "".join(chip(source, "blue", "📌") for source in turn["sources"])
            if source_chips:
                st.markdown(f'<div class="chip-row"><span class="muted">Sources</span>{source_chips}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="muted">No incident IDs were cited in this answer.</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- integration guide
elif active_tab == "Integration guide":
    st.markdown(
        _section_head(
            "Integration guide",
            "Wire this agent to OneUptime and to your own services.",
            chip("Production blueprint", "indigo", "🔌"),
        ),
        unsafe_allow_html=True,
    )

    with st.expander("1 · Run OneUptime locally or on a server", expanded=True):
        st.markdown(
            "OneUptime is an open-source observability, incident management, and status page platform. "
            "Run it on Linux or macOS with Docker Compose:"
        )
        st.code(
            "# Clone the OneUptime repository\n"
            "git clone --depth 1 --single-branch --branch release https://github.com/OneUptime/oneuptime.git\n"
            "cd oneuptime\n\n"
            "# Create your configuration file\n"
            "cp config.example.env config.env\n\n"
            "# Start OneUptime (pulls images and boots services)\n"
            "npm start\n"
            "# Alternatively: docker compose -f docker-compose.yml up -d",
            language="bash",
        )
        st.caption("Once running, visit `http://localhost`. Create an admin account and add your project.")

    with st.expander("2 · Webhook endpoints and Workflows", expanded=False):
        st.markdown(
            "OneUptime Workflows trigger whenever an incident occurs. Point OneUptime at your Hindsight receiver:"
        )
        st.markdown(
            "1. Open OneUptime UI → **Workflows** → **New Workflow** (name it `Hindsight AI Triage`).\n"
            "2. Add Trigger: **On Incident Created**.\n"
            "3. Add Action Component: **API Post (JSON)**.\n"
            "4. Set URL to: `http://<your-agent-ip>:8787/oneuptime/briefing`\n"
            "5. Fill the JSON request body:"
        )
        st.code(
            json.dumps(
                {
                    "id": "{{incident.id}}",
                    "number": "{{incident.incidentNumber}}",
                    "title": "{{incident.title}}",
                    "description": "{{incident.description}}",
                    "service": "{{incident.service.name}}",
                    "severity": "{{incident.incidentSeverity.name}}",
                    "status": "{{incident.currentIncidentState.name}}",
                    "createdAt": "{{incident.createdAt}}",
                    "logs": "{{incident.logs}}",
                    "brief": True,
                },
                indent=2,
            ),
            language="json",
        )
        st.markdown("**Endpoints**")
        st.code(
            "POST http://127.0.0.1:8787/oneuptime          # retain an incident\n"
            "POST http://127.0.0.1:8787/oneuptime/briefing # return an AI briefing",
            language="text",
        )

    with st.expander("3 · Instrument applications with health endpoints", expanded=False):
        st.markdown("Add a `/health` endpoint so OneUptime can monitor it with synthetic HTTP probes:")
        code_tabs = st.tabs(["Node.js (Express)", "Python (FastAPI)", "Go (net/http)", "Kubernetes Probes"])
        with code_tabs[0]:
            st.code(
                "// Express.js health endpoint\n"
                "const express = require('express');\n"
                "const app = express();\n\n"
                "app.get('/health', async (req, res) => {\n"
                "  try {\n"
                "    const dbOk = await checkDatabasePool();\n"
                "    if (!dbOk) {\n"
                "      return res.status(503).json({ status: 'DEGRADED', reason: 'DB pool exhausted' });\n"
                "    }\n"
                "    res.status(200).json({ status: 'UP', timestamp: new Date().toISOString() });\n"
                "  } catch (err) {\n"
                "    res.status(500).json({ status: 'DOWN', error: err.message });\n"
                "  }\n"
                "});\n"
                "app.listen(8080);",
                language="javascript",
            )
        with code_tabs[1]:
            st.code(
                "# FastAPI health endpoint\n"
                "from fastapi import FastAPI, Response, status\n"
                "import datetime\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/health')\n"
                "def health_check(response: Response):\n"
                "    db_healthy = check_db_connection_pool()\n"
                "    if not db_healthy:\n"
                "        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE\n"
                "        return {'status': 'DOWN', 'error': 'Hikari pool timeout'}\n"
                "    return {'status': 'UP', 'time': datetime.datetime.utcnow().isoformat()}",
                language="python",
            )
        with code_tabs[2]:
            st.code(
                "// Go HTTP health endpoint\n"
                "package main\n\n"
                "import (\n"
                '    "net/http"\n'
                ")\n\n"
                "func healthHandler(w http.ResponseWriter, r *http.Request) {\n"
                "    if err := checkHealth(); err != nil {\n"
                '        http.Error(w, `{"status":"DOWN"}`, http.StatusServiceUnavailable)\n'
                "        return\n"
                "    }\n"
                '    w.Header().Set("Content-Type", "application/json")\n'
                "    w.WriteHeader(http.StatusOK)\n"
                '    w.Write([]byte(`{"status":"UP"}`))\n'
                "}",
                language="go",
            )
        with code_tabs[3]:
            st.code(
                "# Kubernetes liveness & readiness probe configuration\n"
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: checkout-api\n"
                "spec:\n"
                "  template:\n"
                "    spec:\n"
                "      containers:\n"
                "      - name: checkout-api\n"
                "        image: myregistry/checkout-api:v3.4.1\n"
                "        ports:\n"
                "        - containerPort: 8080\n"
                "        livenessProbe:\n"
                "          httpGet:\n"
                "            path: /health\n"
                "            port: 8080\n"
                "          initialDelaySeconds: 15\n"
                "          periodSeconds: 10\n"
                "        readinessProbe:\n"
                "          httpGet:\n"
                "            path: /health\n"
                "            port: 8080\n"
                "          initialDelaySeconds: 5\n"
                "          periodSeconds: 5",
                language="yaml",
            )

    with st.expander("4 · The complete production lifecycle", expanded=False):
        st.markdown(
            "1. **Monitor & Detect:** OneUptime synthetic probes continuously ping `/health`.\n"
            "2. **Outage Detected:** The service returns 5xx or latency spikes → OneUptime opens an Incident.\n"
            "3. **Trigger Hindsight:** OneUptime Workflow dispatches JSON alert to Hindsight Webhook.\n"
            "4. **AI Incident Briefing:** Hindsight calls `recall()`, finding matching historical incidents and team policies.\n"
            "5. **Triage in 5 Minutes:** On-call engineer gets the exact fix (e.g. rollback command) and explicit warnings on actions that made it worse before.\n"
            "6. **Post-Mortem & Retain:** Engineer resolves the incident; the resolution and lessons learned are retained (`retain()`), updating team memory for the next outage."
        )

close_toast = st.session_state.pop("close_toast", None)
if close_toast:
    st.toast(close_toast, icon="✅")
