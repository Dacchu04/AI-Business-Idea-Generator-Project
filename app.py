import os
import json
import re
from typing import Dict, Any, List

import streamlit as st

try:
    from google import genai
except Exception:
    genai = None

st.set_page_config(
    page_title="AI Business Idea Generator",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
)



# ---------- AI engine helpers ----------
CORE_SYSTEM_PROMPT = """
You are the Project 21 AI Business Idea Generator.
Generate practical business opportunities from the founder profile, compare them using
explicit criteria, and provide feasibility validation, SWOT, risks, experiments and next steps.
Return ONLY valid JSON matching the requested structure. Do not invent unsupported facts.
Do not reveal private chain-of-thought; provide concise decision rationales.

Return ONLY valid JSON with this top-level structure:
{
  "summary": "short synthesis",
  "candidates": [
    {
      "name": "...",
      "one_liner": "...",
      "problem": "...",
      "customer": "...",
      "solution": "...",
      "rationale": "...",
      "decision": "SHORTLIST or CONSIDER or REJECT",
      "scores": {
        "problem_strength": 0,
        "customer_fit": 0,
        "budget_fit": 0,
        "skill_fit": 0,
        "differentiation": 0,
        "execution_feasibility": 0
      }
    }
  ],
  "shortlist": [
    {
      "name": "...",
      "concept": "...",
      "feasibility_score": 0,
      "target_customer": "...",
      "revenue_model": "...",
      "mvp": ["..."],
      "swot": {
        "strengths": ["..."],
        "weaknesses": ["..."],
        "opportunities": ["..."],
        "threats": ["..."]
      },
      "assumptions": ["..."],
      "risks": [
        {"severity": "Low/Medium/High", "risk": "...", "mitigation": "..."}
      ],
      "validation": ["..."],
      "next_steps": ["..."]
    }
  ]
}

Generate 6 distinct candidates and shortlist up to 3.
Use explicit criteria consistently.
Do not invent specific market statistics, customer counts, revenue figures, laws,
or other facts that were not supplied. State uncertainty where appropriate.
Do not reveal private chain-of-thought. Give concise decision rationales instead.
"""

def build_prompt(profile):
    return f"""
Founder profile:
- Skills: {profile.get("skills", "Not specified")}
- Interests: {profile.get("interests", "Not specified")}
- Available budget: {profile.get("budget", "Not specified")}
- Target customers: {profile.get("customers", "Not specified")}
- Location/market: {profile.get("location", "Not specified")}
- Business preference: {profile.get("preference", "Open to anything")}
- Experience level: {profile.get("experience", "Not specified")}
- Additional business request: {profile.get("additional_request", "None")}

Generate six distinct business opportunities.
Evaluate each on:
1. Problem strength
2. Customer fit
3. Budget fit
4. Skill fit
5. Differentiation
6. Execution feasibility

Then shortlist up to three and provide a business blueprint for each shortlisted idea,
including SWOT, MVP, revenue model, assumptions, risks with mitigations,
validation experiments, and next steps.

Return only the requested JSON structure.
"""
def validate_additional_request(request):
    """
    Project 21 scope guardrail:
    The prototype is specifically designed for business/startup idea generation.
    Returns (True, "") when the request is in scope.
    Returns (False, message) when the request is clearly unrelated or unsafe.
    """
    if not request or not request.strip():
        return True, ""

    text = request.strip().lower()

    # Clearly unsafe / disallowed requests
    blocked_terms = [
        "hack someone's account",
        "hack someone's instagram",
        "steal someone's password",
        "steal password",
        "phishing",
        "malware",
        "ransomware",
        "bypass someone's password",
        "break into someone's account",
    ]

    if any(term in text for term in blocked_terms):
        return False, (
            "This request is outside the supported scope of the prototype. "
            "The AI Business Idea Generator focuses on legitimate business "
            "opportunities, feasibility analysis and startup validation."
        )

    # Terms that indicate a business/startup-related request
    business_terms = [
        "business",
        "startup",
        "start-up",
        "company",
        "venture",
        "idea",
        "business idea",
        "startup idea",
        "opportunity",
        "market",
        "customer",
        "customers",
        "product",
        "service",
        "mvp",
        "revenue",
        "monetize",
        "monetization",
        "sell",
        "selling",
        "saas",
        "app",
        "application",
        "platform",
        "entrepreneur",
        "founder",
        "profit",
        "problem",
        "solution",
    ]

    # If the user explicitly enters a request but it contains
    # no business/startup context, treat it as unsupported.
    if not any(term in text for term in business_terms):
        return False, (
            "This request is outside the supported scope of Project 21. "
            "Please provide a business or startup-related request, such as "
            "a target market, customer problem, product idea, revenue model "
            "or business opportunity."
        )

    return True, ""

def score_idea(candidate):
    scores = candidate.get("scores", {})
    values = []
    for key in [
        "problem_strength",
        "customer_fit",
        "budget_fit",
        "skill_fit",
        "differentiation",
        "execution_feasibility",
    ]:
        try:
            values.append(float(scores.get(key, 0)))
        except (TypeError, ValueError):
            values.append(0.0)
    return sum(values) / len(values) if values else 0.0

def get_demo_data(profile):
    skills = profile.get("skills", "general skills")
    customers = profile.get("customers", "target customers")
    ideas = [
        {
            "name": "AI Workflow Copilot",
            "one_liner": f"An AI workflow assistant for {customers}.",
            "problem": "Small teams lose time on repetitive research, drafting and coordination.",
            "customer": customers,
            "solution": "A focused AI workspace that automates recurring knowledge-work tasks.",
            "rationale": "Strong alignment with AI/productivity interests and a software-first MVP.",
            "decision": "SHORTLIST",
            "scores": {
                "problem_strength": 8, "customer_fit": 8, "budget_fit": 9,
                "skill_fit": 9, "differentiation": 7, "execution_feasibility": 8
            }
        },
        {
            "name": "Skill-to-Service Studio",
            "one_liner": f"Turn {skills} into packaged digital services for small businesses.",
            "problem": "Small businesses often need technical help without hiring full-time specialists.",
            "customer": "Small businesses",
            "solution": "Productized services with clear packages, delivery timelines and recurring support.",
            "rationale": "Can start with low infrastructure cost and validate demand manually.",
            "decision": "SHORTLIST",
            "scores": {
                "problem_strength": 8, "customer_fit": 8, "budget_fit": 10,
                "skill_fit": 9, "differentiation": 6, "execution_feasibility": 9
            }
        },
        {
            "name": "AI Study Planner",
            "one_liner": "Personalized study planning and revision support for students.",
            "problem": "Students struggle to turn large syllabi into realistic daily study plans.",
            "customer": "Students",
            "solution": "AI-generated schedules, revision checkpoints and progress-based adjustments.",
            "rationale": "Clear user problem and easy-to-demo AI workflow.",
            "decision": "SHORTLIST",
            "scores": {
                "problem_strength": 8, "customer_fit": 8, "budget_fit": 9,
                "skill_fit": 8, "differentiation": 6, "execution_feasibility": 9
            }
        },
        {
            "name": "Local Business Content Engine",
            "one_liner": "AI-assisted content planning for local businesses.",
            "problem": "Local businesses often struggle to maintain consistent digital content.",
            "customer": "Local businesses",
            "solution": "Generate content calendars, post drafts and campaign ideas from a business profile.",
            "rationale": "Simple MVP with a clear service-to-software path.",
            "decision": "CONSIDER",
            "scores": {
                "problem_strength": 7, "customer_fit": 7, "budget_fit": 9,
                "skill_fit": 8, "differentiation": 6, "execution_feasibility": 9
            }
        },
        {
            "name": "AI Research Brief Builder",
            "one_liner": "Convert supplied research material into structured decision briefs.",
            "problem": "Teams spend time organizing long information into usable summaries.",
            "customer": "Students, analysts and small teams",
            "solution": "A structured workspace for turning supplied material into concise briefs.",
            "rationale": "Fits prompt-engineering strengths while keeping the MVP focused.",
            "decision": "CONSIDER",
            "scores": {
                "problem_strength": 7, "customer_fit": 7, "budget_fit": 9,
                "skill_fit": 8, "differentiation": 7, "execution_feasibility": 8
            }
        },
        {
            "name": "Founder Validation Assistant",
            "one_liner": "A guided AI workspace for testing early business assumptions.",
            "problem": "Early founders can struggle to turn an idea into testable assumptions.",
            "customer": "Early-stage founders",
            "solution": "Generate assumptions, customer interview questions and lightweight validation experiments.",
            "rationale": "Directly complements the Project 21 feasibility-validation workflow.",
            "decision": "CONSIDER",
            "scores": {
                "problem_strength": 8, "customer_fit": 7, "budget_fit": 9,
                "skill_fit": 8, "differentiation": 8, "execution_feasibility": 8
            }
        }
    ]

    shortlist_names = {"AI Workflow Copilot", "Skill-to-Service Studio", "AI Study Planner"}
    shortlist = []
    for idea in ideas:
        if idea["name"] in shortlist_names:
            shortlist.append({
                "name": idea["name"],
                "concept": idea["one_liner"],
                "feasibility_score": round(score_idea(idea), 1),
                "target_customer": idea["customer"],
                "revenue_model": "Subscription, packaged service, or usage-based pricing depending on validation.",
                "mvp": [
                    "Founder profile and onboarding form",
                    "Core AI workflow",
                    "Structured results dashboard",
                    "Feedback and validation loop"
                ],
                "swot": {
                    "strengths": ["Low initial infrastructure needs", "Clear AI-enabled workflow"],
                    "weaknesses": ["Requires differentiation", "Output quality depends on inputs"],
                    "opportunities": ["Niche customer specialization", "Recurring workflow automation"],
                    "threats": ["Crowded AI tooling market", "Changing model capabilities"]
                },
                "assumptions": [
                    "The target users experience the stated problem regularly.",
                    "Users value a focused workflow over a generic AI chatbot."
                ],
                "risks": [
                    {
                        "severity": "Medium",
                        "risk": "Users may not perceive enough differentiation.",
                        "mitigation": "Interview target users and test a narrow workflow before building more features."
                    },
                    {
                        "severity": "Medium",
                        "risk": "AI outputs may require human review.",
                        "mitigation": "Use structured validation and make important assumptions explicit."
                    }
                ],
                "validation": [
                    "Interview 5–10 target users about the problem.",
                    "Create a lightweight landing page or prototype.",
                    "Test whether users complete the core workflow and request repeat use."
                ],
                "next_steps": [
                    "Select one narrow customer segment.",
                    "Build the smallest usable MVP.",
                    "Run user interviews and collect structured feedback.",
                    "Measure repeat usage before expanding the product."
                ]
            })

    return {
        "summary": "Demo Mode: six candidate opportunities generated and compared using the Project 21 evaluation framework.",
        "candidates": ideas,
        "shortlist": shortlist
    }

def get_ai_data(profile):
    """Call Gemini when a key is available; otherwise use the local demo."""
    key = None

    try:
        key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass

    key = key or os.getenv("GEMINI_API_KEY")

    if not key or genai is None:
        return get_demo_data(profile), "Demo"

    try:
        client = genai.Client(api_key=key)

        model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        prompt = CORE_SYSTEM_PROMPT + "\n\n" + build_prompt(profile)

        # Gemini structured output keeps the application response predictable.
        response = client.interactions.create(
            model=model,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": {
                    "type": "OBJECT",
                    "properties": {
                        "summary": {"type": "STRING"},
                        "candidates": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING"},
                                    "one_liner": {"type": "STRING"},
                                    "problem": {"type": "STRING"},
                                    "customer": {"type": "STRING"},
                                    "solution": {"type": "STRING"},
                                    "rationale": {"type": "STRING"},
                                    "decision": {"type": "STRING"},
                                    "scores": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "problem_strength": {"type": "NUMBER"},
                                            "customer_fit": {"type": "NUMBER"},
                                            "budget_fit": {"type": "NUMBER"},
                                            "skill_fit": {"type": "NUMBER"},
                                            "differentiation": {"type": "NUMBER"},
                                            "execution_feasibility": {"type": "NUMBER"}
                                        },
                                        "required": [
                                            "problem_strength",
                                            "customer_fit",
                                            "budget_fit",
                                            "skill_fit",
                                            "differentiation",
                                            "execution_feasibility"
                                        ]
                                    }
                                },
                                "required": [
                                    "name", "one_liner", "problem", "customer",
                                    "solution", "rationale", "decision", "scores"
                                ]
                            }
                        },
                        "shortlist": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING"},
                                    "concept": {"type": "STRING"},
                                    "feasibility_score": {"type": "NUMBER"},
                                    "target_customer": {"type": "STRING"},
                                    "revenue_model": {"type": "STRING"},
                                    "mvp": {
                                        "type": "ARRAY",
                                        "items": {"type": "STRING"}
                                    },
                                    "swot": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "strengths": {
                                                "type": "ARRAY",
                                                "items": {"type": "STRING"}
                                            },
                                            "weaknesses": {
                                                "type": "ARRAY",
                                                "items": {"type": "STRING"}
                                            },
                                            "opportunities": {
                                                "type": "ARRAY",
                                                "items": {"type": "STRING"}
                                            },
                                            "threats": {
                                                "type": "ARRAY",
                                                "items": {"type": "STRING"}
                                            }
                                        },
                                        "required": [
                                            "strengths", "weaknesses",
                                            "opportunities", "threats"
                                        ]
                                    },
                                    "assumptions": {
                                        "type": "ARRAY",
                                        "items": {"type": "STRING"}
                                    },
                                    "risks": {
                                        "type": "ARRAY",
                                        "items": {
                                            "type": "OBJECT",
                                            "properties": {
                                                "severity": {"type": "STRING"},
                                                "risk": {"type": "STRING"},
                                                "mitigation": {"type": "STRING"}
                                            },
                                            "required": [
                                                "severity", "risk", "mitigation"
                                            ]
                                        }
                                    },
                                    "validation": {
                                        "type": "ARRAY",
                                        "items": {"type": "STRING"}
                                    },
                                    "next_steps": {
                                        "type": "ARRAY",
                                        "items": {"type": "STRING"}
                                    }
                                },
                                "required": [
                                    "name", "concept", "feasibility_score",
                                    "target_customer", "revenue_model", "mvp",
                                    "swot", "assumptions", "risks",
                                    "validation", "next_steps"
                                ]
                            }
                        }
                    },
                    "required": ["summary", "candidates", "shortlist"]
                }
            }
        )

        content = getattr(response, "output_text", None)
        if not content:
            raise ValueError("Gemini returned an empty response.")

        data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError("Gemini returned an unexpected JSON structure.")

        if not isinstance(data.get("candidates"), list):
            raise ValueError("Gemini response is missing the candidates list.")

        if not isinstance(data.get("shortlist"), list):
            data["shortlist"] = []

        return data, "Live AI · Gemini"

    except Exception as exc:
        error_text = str(exc)
        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text or "too_many_requests" in error_text:
            st.warning(
                "Gemini free-tier rate limit reached. Please wait a short time and try once again. "
                "The prototype has switched to Demo Mode so the workflow remains usable."
            )
        else:
            st.warning(
                f"Gemini request failed, so the prototype switched to Demo Mode: {exc}"
            )
        return get_demo_data(profile), "Demo (fallback)"


# ---------- Premium product UI ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
  --ink:#101828; --muted:#667085; --line:#e8eaf0; --surface:#ffffff;
  --bg:#f5f7fb; --violet:#6d5dfc; --cyan:#22d3ee; --pink:#ec4899;
}
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 10% 0%, rgba(109,93,252,.10), transparent 27%),
    radial-gradient(circle at 90% 8%, rgba(34,211,238,.09), transparent 24%),
    var(--bg);
}
[data-testid="stHeader"] { background:rgba(245,247,251,.78); }
.block-container { max-width:1480px; padding:1.2rem 2.1rem 3.2rem; }

/* Animated ambient background */
[data-testid="stAppViewContainer"]::before,
[data-testid="stAppViewContainer"]::after {
  content:""; position:fixed; width:240px; height:240px; border-radius:50%;
  pointer-events:none; filter:blur(60px); opacity:.20; z-index:0;
  animation:floatOrb 11s ease-in-out infinite alternate;
}
[data-testid="stAppViewContainer"]::before { background:#7c3aed; left:-90px; top:35%; }
[data-testid="stAppViewContainer"]::after { background:#06b6d4; right:-100px; top:65%; animation-delay:-4s; }
@keyframes floatOrb { from{transform:translate3d(0,0,0) scale(1)} to{transform:translate3d(35px,-25px,0) scale(1.15)} }

/* Hero */
.hero {
  position:relative; overflow:hidden; border-radius:28px; padding:38px 42px 40px;
  color:#fff; margin:4px 0 25px;
  background:
    radial-gradient(circle at 84% 25%, rgba(34,211,238,.26), transparent 25%),
    radial-gradient(circle at 65% 90%, rgba(236,72,153,.20), transparent 30%),
    linear-gradient(135deg,#0b1020 0%,#171a3b 48%,#25204e 100%);
  box-shadow:0 26px 70px rgba(16,24,40,.20);
}
.hero::before {
  content:""; position:absolute; width:340px; height:340px; border:1px solid rgba(255,255,255,.12);
  border-radius:50%; right:-110px; top:-150px; box-shadow:0 0 0 42px rgba(255,255,255,.025),0 0 0 84px rgba(255,255,255,.018);
}
.hero::after {
  content:""; position:absolute; width:130px; height:130px; border-radius:50%;
  background:linear-gradient(135deg,rgba(109,93,252,.75),rgba(34,211,238,.25));
  filter:blur(2px); right:11%; bottom:-70px; transform:rotate(20deg);
  animation:heroFloat 7s ease-in-out infinite alternate;
}
@keyframes heroFloat { to{transform:translateY(-22px) rotate(32deg)} }
.hero-content { position:relative; z-index:2; max-width:920px; }
.badge {
  display:inline-flex; gap:7px; align-items:center; padding:7px 12px; border-radius:999px;
  border:1px solid rgba(255,255,255,.16); background:rgba(255,255,255,.08);
  color:#dfe4ff; font-size:.70rem; font-weight:700; letter-spacing:.09em;
}
.live-dot { width:7px; height:7px; border-radius:50%; background:#34d399; box-shadow:0 0 12px #34d399; }
.hero h1 { font-family:'Space Grotesk',sans-serif; font-size:clamp(2.3rem,4vw,4.1rem); line-height:1.02; letter-spacing:-2.8px; margin:20px 0 13px; }
.hero h1 span { background:linear-gradient(90deg,#fff,#b9c6ff 50%,#79e8ff); -webkit-background-clip:text; background-clip:text; color:transparent; }
.hero p { color:#c9cee1; font-size:1.02rem; line-height:1.65; max-width:760px; margin:0; }
.hero-meta { display:flex; gap:9px; flex-wrap:wrap; margin-top:22px; }
.hero-chip { padding:7px 11px; border-radius:10px; background:rgba(255,255,255,.07); color:#d8dced; border:1px solid rgba(255,255,255,.09); font-size:.75rem; }

/* Sidebar */
section[data-testid="stSidebar"] {
  background:linear-gradient(180deg,#0d1222,#11172a);
  border-right:1px solid rgba(255,255,255,.06);
}
section[data-testid="stSidebar"] * { color:#e8ebf4; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
  background:#171e32 !important; border-color:#2c3652 !important; color:#fff !important;
  border-radius:11px !important;
}
section[data-testid="stSidebar"] label { font-size:.76rem !important; font-weight:600 !important; color:#b9c1d5 !important; }
.sidebar-brand { padding:8px 0 22px; }
.sidebar-logo {
 display:inline-flex; width:38px; height:38px; align-items:center; justify-content:center;
 border-radius:12px; background:linear-gradient(135deg,#6d5dfc,#22d3ee);
 box-shadow:0 10px 28px rgba(109,93,252,.32); font-size:1.1rem;
}
.sidebar-title { font-family:'Space Grotesk'; font-weight:700; font-size:1.03rem; margin-left:9px; vertical-align:middle; }
.sidebar-sub { color:#8e98b0 !important; font-size:.72rem; margin-top:8px; line-height:1.5; }
.framework {
  padding:13px; border:1px solid #27314a; border-radius:14px; background:#131a2d; margin-top:12px;
}
.framework-step { display:flex; gap:9px; margin:8px 0; font-size:.72rem; color:#c7cede !important; }
.step-dot { width:7px;height:7px;border-radius:50%;background:#7c6cff;margin-top:5px;flex:none; }

/* Inputs and buttons */
.stButton > button {
  border-radius:13px !important; min-height:46px !important; font-weight:700 !important;
  border:0 !important; transition:all .22s ease !important;
}
.stButton > button:hover { transform:translateY(-2px); box-shadow:0 12px 28px rgba(109,93,252,.22); }
button[kind="primary"] {
  background:linear-gradient(135deg,#6d5dfc,#4f46e5) !important;
  color:#fff !important;
}
.stDownloadButton > button { border-radius:12px !important; }

/* Metrics */
div[data-testid="stMetric"] {
  background:rgba(255,255,255,.88); border:1px solid var(--line); border-radius:17px;
  padding:16px 18px; box-shadow:0 10px 28px rgba(16,24,40,.045);
}
div[data-testid="stMetricLabel"] { color:#667085 !important; font-weight:600; }
div[data-testid="stMetricValue"] { font-family:'Space Grotesk'; color:#101828; }

/* Cards */
.section-title { font-family:'Space Grotesk'; font-size:1.28rem; font-weight:700; color:var(--ink); margin:14px 0 12px; }
.card {
 background:rgba(255,255,255,.90); border:1px solid var(--line); border-radius:19px; padding:20px;
 box-shadow:0 9px 30px rgba(16,24,40,.045); margin-bottom:14px;
 transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease;
}
.card:hover { transform:translateY(-2px); box-shadow:0 18px 42px rgba(16,24,40,.08); border-color:#d9dcf2; }
.insight { border-left:4px solid #6d5dfc; background:#f5f4ff; padding:13px 16px; border-radius:11px; color:#344054; }
.muted { color:#667085; }
.small-label { text-transform:uppercase; letter-spacing:.09em; font-size:.67rem; font-weight:700; color:#98a2b3; }
.idea-title { font-family:'Space Grotesk'; font-size:1.25rem; font-weight:700; color:#101828; }
.score { font-family:'Space Grotesk'; font-size:1.7rem; font-weight:700; color:#101828; }
.pill { display:inline-block; border-radius:999px; padding:5px 9px; margin:2px 4px 2px 0; background:#f0f2f7; color:#475467; font-size:.72rem; font-weight:600; }

/* Expander / tabs */
[data-testid="stExpander"] { border:1px solid var(--line) !important; border-radius:15px !important; background:rgba(255,255,255,.84) !important; overflow:hidden; }
button[data-baseweb="tab"] { font-weight:700 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color:#5b4ff0 !important; }

/* Progress */
div[data-testid="stProgress"] > div > div > div { background:linear-gradient(90deg,#6d5dfc,#22d3ee); }

/* Footer */
.footer { text-align:center; color:#98a2b3; font-size:.72rem; padding:34px 0 6px; }

/* ---------- Visibility / accessibility fix ----------
   The app uses a light main canvas with a dark sidebar. Force Streamlit's
   native widgets to use a matching light theme so text cannot become white
   on white when the browser/system prefers dark mode.
*/
:root {
  color-scheme: light;
  --app-text: #101828;
  --app-muted: #475467;
  --app-surface: #ffffff;
  --app-border: #d9dee8;
}

[data-testid="stAppViewContainer"] *,
[data-testid="stMain"] * {
  color-scheme: light;
}

/* Native Streamlit text */
[data-testid="stMain"] p,
[data-testid="stMain"] label,
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4,
[data-testid="stMain"] h5,
[data-testid="stMain"] h6,
[data-testid="stMain"] li,
[data-testid="stMain"] span {
  color: var(--app-text);
}

/* Keep the custom hero's intended light text */
.hero,
.hero * {
  color: inherit;
}
.hero p { color: #c9cee1 !important; }
.hero h1 { color: #fff !important; }
.hero h1 span { color: transparent !important; }

/* Metrics */
div[data-testid="stMetric"],
div[data-testid="stMetric"] * {
  opacity: 1 !important;
}
div[data-testid="stMetricLabel"] *,
div[data-testid="stMetricValue"] *,
div[data-testid="stMetricDelta"] * {
  color: #101828 !important;
}

/* Tabs */
button[data-baseweb="tab"],
button[data-baseweb="tab"] * {
  color: #344054 !important;
  opacity: 1 !important;
}
button[data-baseweb="tab"][aria-selected="true"],
button[data-baseweb="tab"][aria-selected="true"] * {
  color: #5b4ff0 !important;
}

/* Expanders — this is the main area visible in the screenshot */
[data-testid="stExpander"],
[data-testid="stExpander"] * {
  opacity: 1 !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary *,
[data-testid="stExpander"] button,
[data-testid="stExpander"] button * {
  color: #101828 !important;
}
[data-testid="stExpander"] {
  background: #ffffff !important;
  border: 1px solid #d9dee8 !important;
}
[data-testid="stExpander"] summary:hover {
  background: #f8f9fc !important;
}

/* Native warnings/info/status */
[data-testid="stAlert"],
[data-testid="stAlert"] * {
  opacity: 1 !important;
}

/* Export heading and normal Streamlit markdown */
[data-testid="stMarkdownContainer"] {
  opacity: 1 !important;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
  color: #344054;
}

/* Keep sidebar styling dark */
section[data-testid="stSidebar"] *,
section[data-testid="stSidebar"] label {
  color: #e8ebf4 !important;
}
section[data-testid="stSidebar"] .sidebar-sub,
section[data-testid="stSidebar"] .framework-step {
  color: #c7cede !important;
}

</style>
""", unsafe_allow_html=True)

# ---------- Session state ----------
if "result" not in st.session_state: st.session_state.result = None
if "profile" not in st.session_state: st.session_state.profile = None
if "mode" not in st.session_state: st.session_state.mode = None

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
      <span class="sidebar-logo">💡</span>
      <span class="sidebar-title">Idea Generator</span>
      <div class="sidebar-sub">PROJECT 21 · GEMINI BUSINESS OPPORTUNITY ENGINE</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Founder profile")
    skills = st.text_input("Skills", "Python, AI/ML, web development")
    interests = st.text_input("Interests", "AI, education, productivity")
    budget = st.selectbox("Available budget", ["Under ₹50,000", "₹50,000–₹2 lakh", "₹2–₹10 lakh", "₹10 lakh+"])
    customers = st.text_input("Target customers", "Students and small businesses")
    location = st.text_input("Location / market", "India")
    
    additional_request = st.text_area(
        "Additional business request (optional)",
        "",
        placeholder="Example: I want a low-cost AI business idea for college students.",
        height=90,
        help="Optional. Keep the request related to business or startup opportunities."
    )

    preference = st.selectbox(
        "Business preference",
        ["B2B SaaS", "B2C", "Marketplace", "Service business", "Open to anything"]
    )
    experience = st.selectbox("Experience level", ["Beginner", "Intermediate", "Advanced"])

    st.markdown("""
    <div class="framework">
      <div style="font-weight:700;font-size:.78rem;margin-bottom:9px">AI decision pipeline</div>
      <div class="framework-step"><span class="step-dot"></span>Generate candidate opportunities</div>
      <div class="framework-step"><span class="step-dot"></span>Compare with explicit criteria</div>
      <div class="framework-step"><span class="step-dot"></span>Validate feasibility</div>
      <div class="framework-step"><span class="step-dot"></span>Build SWOT + risk profile</div>
      <div class="framework-step"><span class="step-dot"></span>Design validation experiments</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")
    generate = st.button("✨  Generate opportunities", type="primary", use_container_width=True)

# ---------- Hero ----------
st.markdown("""
<div class="hero">
  <div class="hero-content">
    <div class="badge"><span class="live-dot"></span> PROJECT 21 · GENERATIVE AI CAPSTONE</div>
    <h1>AI Business <span>Idea Generator</span></h1>
    <p>Discover business opportunities from your skills, interests and constraints — then
    compare, stress-test and turn the strongest concepts into actionable startup blueprints.</p>
    <div class="hero-meta">
      <span class="hero-chip">✦ Multi-idea generation</span>
      <span class="hero-chip">◈ Structured evaluation</span>
      <span class="hero-chip">◇ SWOT intelligence</span>
      <span class="hero-chip">◎ Feasibility validation</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------- Generate ----------
if generate:
    missing_fields = []

    if not skills.strip():
        missing_fields.append("Skills")

    if not interests.strip():
        missing_fields.append("Interests")

    if not customers.strip():
        missing_fields.append("Target customers")

    if not location.strip():
        missing_fields.append("Location / market")

    if missing_fields:
        st.error(
            "Please complete the following required fields before generating: "
            + ", ".join(missing_fields),
            icon="⚠️"
        )
        st.stop()

    # ---------- Scope guardrail ----------
    request_is_valid, guardrail_message = validate_additional_request(
        additional_request
    )

    if not request_is_valid:
        st.error(
            guardrail_message,
            icon="🛡️"
        )
        st.info(
            "Supported scope: business ideas, startup opportunities, "
            "customer problems, products, services, MVPs, revenue models "
            "and feasibility validation."
        )
        st.stop()

    profile = {
        "skills": skills.strip(),
        "interests": interests.strip(),
        "budget": budget,
        "customers": customers.strip(),
        "location": location.strip(),
        "preference": preference,
        "experience": experience,
        "additional_request": additional_request.strip(),
    }

    st.session_state.profile = profile

    with st.spinner("Generating, comparing and validating opportunities…"):
        result, mode = get_ai_data(profile)

    st.session_state.result = result
    st.session_state.mode = mode

# ---------- Empty state ----------
if not st.session_state.result:
    st.markdown(
        '<div class="section-title">Your opportunity workspace</div>',
        unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidate ideas", "06")
    c2.metric("Shortlist", "≤ 03")
    c3.metric("Evaluation criteria", "06")
    c4.metric("Output layers", "05")

    st.markdown("""
    <div class="card">
      <div class="small-label">START HERE</div>
      <div class="idea-title" style="margin-top:7px">
        Describe the founder behind the idea.
      </div>
      <p class="muted">
        Use the profile controls on the left. The engine will generate several
        distinct opportunities, compare them consistently, and turn the shortlisted
        concepts into detailed business blueprints.
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.info(
        "For a strong demo, use a specific customer segment, realistic budget, "
        "concrete skills and a business preference."
    )

    st.markdown(
        '<div class="footer">AI Business Idea Generator · Project 21 · Prototype</div>',
        unsafe_allow_html=True
    )

    st.stop()


# ---------- Load generated data ----------
result = st.session_state.result
profile = st.session_state.profile
candidates = result.get("candidates", [])
shortlist = result.get("shortlist", [])


# ---------- Dashboard ----------
scores = [score_idea(c) for c in candidates]
avg = sum(scores) / len(scores) if scores else 0
avg = sum(scores)/len(scores) if scores else 0
st.markdown('<div class="section-title">Opportunity intelligence</div>', unsafe_allow_html=True)
m1,m2,m3,m4 = st.columns(4)
m1.metric("Ideas generated", f"{len(candidates):02d}")
m2.metric("Shortlisted", f"{len(shortlist):02d}")
m3.metric("Avg. feasibility", f"{avg:.1f}/10")
m4.metric("Engine status", st.session_state.mode or "Demo")

st.markdown(f"""
<div class="card">
  <div class="small-label">AI SYNTHESIS</div>
  <div style="font-size:1.0rem;font-weight:600;color:#344054;margin-top:7px">{result.get("summary","")}</div>
</div>
""", unsafe_allow_html=True)

tab1,tab2,tab3 = st.tabs(["✦ Opportunity comparison", "🚀 Shortlist blueprints", "🧪 Validation lab"])

# ---------- Comparison ----------
with tab1:
    for rank,c in enumerate(sorted(candidates,key=score_idea,reverse=True),1):
        s=score_idea(c)
        decision=c.get("decision","").upper()
        with st.expander(f"#{rank}   {c.get('name','Idea')}   ·   {s:.1f}/10   ·   {decision}"):
            left,right=st.columns([1.25,1])
            with left:
                st.markdown(f'<div class="idea-title">{c.get("one_liner","")}</div>',unsafe_allow_html=True)
                st.write(c.get("rationale",""))
                st.markdown(f'<div class="insight"><b>Problem:</b> {c.get("problem","")}<br><br><b>Customer:</b> {c.get("customer","")}<br><br><b>Solution:</b> {c.get("solution","")}</div>',unsafe_allow_html=True)
            with right:
                st.markdown('<div class="small-label">FEASIBILITY SIGNALS</div>',unsafe_allow_html=True)
                for k,v in c.get("scores",{}).items():
                    st.progress(min(1,float(v)/10),text=f"{k.replace('_',' ').title()}  ·  {v}/10")

# ---------- Deep dive ----------
with tab2:
    if not shortlist:
        st.warning("No ideas were shortlisted. Refine the profile and generate again.")
    for idx,idea in enumerate(shortlist):
        st.markdown(f"### {idx+1}. {idea.get('name','Business idea')}")
        st.markdown(f'<div class="insight">{idea.get("concept","")}</div>',unsafe_allow_html=True)
        a,b,c=st.columns(3)
        a.metric("Feasibility",f"{idea.get('feasibility_score',0)}/10")
        b.metric("Target",idea.get("target_customer","—"))
        c.metric("Revenue model",idea.get("revenue_model","—"))
        l,r=st.columns(2)
        with l:
            st.markdown("#### MVP")
            for x in idea.get("mvp",[]): st.markdown(f"• {x}")
            st.markdown("#### Strengths")
            for x in idea.get("swot",{}).get("strengths",[]): st.markdown(f"• {x}")
            st.markdown("#### Weaknesses")
            for x in idea.get("swot",{}).get("weaknesses",[]): st.markdown(f"• {x}")
        with r:
            st.markdown("#### Opportunities")
            for x in idea.get("swot",{}).get("opportunities",[]): st.markdown(f"• {x}")
            st.markdown("#### Threats")
            for x in idea.get("swot",{}).get("threats",[]): st.markdown(f"• {x}")
            st.markdown("#### Assumptions")
            for x in idea.get("assumptions",[]): st.markdown(f"• {x}")
        st.divider()

# ---------- Validation lab ----------
with tab3:
    if not shortlist:
        st.warning("No shortlisted concept available.")
    else:
        names=[x.get("name","Idea") for x in shortlist]
        selected=st.selectbox("Select an opportunity to stress-test",names)
        idea=next(x for x in shortlist if x.get("name")==selected)
        st.markdown("#### ⚠️ Risk stress test")
        for r in idea.get("risks",[]):
            st.markdown(f"**{r.get('severity','Medium')} · {r.get('risk','Risk')}**")
            st.caption(r.get("mitigation",""))
        st.markdown("#### Validation experiments")
        for i,x in enumerate(idea.get("validation",[]),1): st.markdown(f"**{i}.** {x}")
        st.markdown("#### Recommended next steps")
        for x in idea.get("next_steps",[]): st.markdown(f"• {x}")
        st.markdown("""<div class="card"><b>Validation discipline</b><br>
        <span class="muted">AI-generated opportunities are hypotheses, not proof of demand,
        profitability or market size. Validate customer pain, willingness to pay, competition
        and execution assumptions before committing significant resources.</span></div>""",unsafe_allow_html=True)

# ---------- Export ----------
st.divider()
st.markdown('<div class="section-title">Export your analysis</div>',unsafe_allow_html=True)
export={"project":"AI Business Idea Generator","profile":profile,"result":result,
        "framework":{"advanced_prompting":"Tree of Thoughts-inspired branching and comparison",
                     "grounding":"Prompt Engineering","guardrail":"Feasibility validation"}}
st.download_button("↓  Download analysis JSON",data=json.dumps(export,indent=2,ensure_ascii=False),
                   file_name="ai_business_idea_analysis.json",mime="application/json")
st.markdown('<div class="footer">AI Business Idea Generator · Project 21 · Built as a deployable Generative AI prototype · Gemini</div>',unsafe_allow_html=True)
