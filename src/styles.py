"""
🎨 Sistema de estilos do Caçador de Concursos IA.
CSS customizado injetado via st.markdown para elevar o visual do Streamlit.
"""
import html
import streamlit as st

# ==========================================
# PALETA DE CORES
# ==========================================
COLORS = {
    "primary": "#4F46E5",
    "primary_light": "#818CF8",
    "primary_bg": "#EEF2FF",
    "success": "#059669",
    "success_bg": "#ECFDF5",
    "warning": "#D97706",
    "warning_bg": "#FFFBEB",
    "danger": "#DC2626",
    "danger_bg": "#FEF2F2",
    "text": "#1E293B",
    "text_muted": "#64748B",
    "bg": "#F8FAFC",
    "card": "#FFFFFF",
    "border": "#E2E8F0",
}


# ==========================================
# CSS GLOBAL
# ==========================================
GLOBAL_CSS = """
<style>
/* ---- Google Font ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ---- Root ---- */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* ---- Hero Section ---- */
.hero-card {
    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    color: white;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.hero-card::after {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 300px;
    height: 300px;
    background: rgba(255,255,255,0.06);
    border-radius: 50%;
}
.hero-card h1 {
    margin: 0 0 0.3rem 0;
    font-size: 1.8rem;
    font-weight: 700;
    color: white !important;
}
.hero-card p {
    margin: 0;
    opacity: 0.9;
    font-size: 1rem;
}
.hero-badge {
    display: inline-block;
    background: rgba(255,255,255,0.2);
    backdrop-filter: blur(4px);
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    letter-spacing: 0.02em;
}

/* ---- Cards (Streamlit containers) ---- */
div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06) !important;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.06) !important;
    transform: translateY(-1px);
}

/* ---- Stat Cards ---- */
.stat-card {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.2rem 1rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.stat-card .stat-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #1E293B;
    line-height: 1.2;
}
.stat-card .stat-label {
    font-size: 0.8rem;
    color: #64748B;
    margin-top: 0.2rem;
    font-weight: 500;
}
.stat-card .stat-icon {
    font-size: 1.5rem;
    margin-bottom: 0.3rem;
}

/* ---- Badges de status ---- */
.badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    margin-right: 0.3rem;
    margin-bottom: 0.2rem;
}
.badge-open {
    background: #ECFDF5;
    color: #059669;
    border: 1px solid #A7F3D0;
}
.badge-closed {
    background: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
}
.badge-subscribed {
    background: #EEF2FF;
    color: #4F46E5;
    border: 1px solid #C7D2FE;
}
.badge-urgent {
    background: #FFFBEB;
    color: #D97706;
    border: 1px solid #FDE68A;
    animation: pulse-badge 2s ease-in-out infinite;
}
@keyframes pulse-badge {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

/* ---- Chips de profissão ---- */
.chip {
    display: inline-block;
    background: #EEF2FF;
    color: #4F46E5;
    border: 1px solid #C7D2FE;
    padding: 0.3rem 0.8rem;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 500;
    margin: 0.15rem 0.2rem;
}

/* ---- Chips de habilidade ---- */
.skill-found {
    display: inline-block;
    background: #ECFDF5;
    color: #059669;
    border: 1px solid #A7F3D0;
    padding: 0.2rem 0.6rem;
    border-radius: 16px;
    font-size: 0.75rem;
    font-weight: 500;
    margin: 0.1rem 0.15rem;
}
.skill-missing {
    display: inline-block;
    background: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
    padding: 0.2rem 0.6rem;
    border-radius: 16px;
    font-size: 0.75rem;
    font-weight: 500;
    margin: 0.1rem 0.15rem;
}

/* ---- Barra de match (CV) ---- */
.match-bar-container {
    background: #F1F5F9;
    border-radius: 8px;
    height: 10px;
    overflow: hidden;
    margin: 0.5rem 0;
}
.match-bar {
    height: 100%;
    border-radius: 8px;
    transition: width 0.6s ease;
}
.match-bar.high { background: linear-gradient(90deg, #059669, #34D399); }
.match-bar.medium { background: linear-gradient(90deg, #D97706, #FBBF24); }
.match-bar.low { background: linear-gradient(90deg, #DC2626, #F87171); }

.match-percent {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
}
.match-percent.high { color: #059669; }
.match-percent.medium { color: #D97706; }
.match-percent.low { color: #DC2626; }

/* ---- Info badges inline ---- */
.info-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    align-items: center;
    margin: 0.3rem 0;
}
.info-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: #F1F5F9;
    color: #475569;
    padding: 0.25rem 0.6rem;
    border-radius: 8px;
    font-size: 0.78rem;
    font-weight: 500;
}

/* ---- Sidebar polish ---- */
section[data-testid="stSidebar"] {
    background: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
}
section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 8px;
    font-weight: 500;
    border: 1px solid #E2E8F0;
    transition: all 0.2s ease;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #4F46E5;
    color: #4F46E5;
}

/* ---- Primary button ---- */
button[kind="primary"] {
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.5rem !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3) !important;
}

/* ---- Section headers ---- */
.section-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 1.5rem 0 0.8rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #EEF2FF;
}
.section-header h2 {
    margin: 0;
    font-size: 1.3rem;
    font-weight: 600;
    color: #1E293B;
}

/* ---- Data editor / table ---- */
div[data-testid="stDataEditor"] {
    border-radius: 12px !important;
    overflow: hidden;
    border: 1px solid #E2E8F0 !important;
}

/* ---- Tab polish ---- */
button[data-baseweb="tab"] {
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    padding: 0.7rem 1.2rem !important;
}

/* ---- Fade-in animation ---- */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.fade-in {
    animation: fadeInUp 0.35s ease-out forwards;
}

/* ---- Expander polish ---- */
details[data-testid="stExpander"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
}

/* ---- Hide default header decoration ---- */
header[data-testid="stHeader"] {
    background: transparent !important;
}
</style>
"""


# ==========================================
# HELPERS DE RENDERIZAÇÃO
# ==========================================
def inject_css():
    """Injeta o CSS global na página. Chamar uma vez no topo de cada página."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, badge: str = ""):
    """Renderiza o hero card no topo da página."""
    badge_html = f'<span class="hero-badge">{badge}</span><br>' if badge else ""
    st.markdown(
        f"""<div class="hero-card fade-in">
{badge_html}
<div style="margin:0 0 0.3rem 0;font-size:1.8rem;font-weight:700;color:white;">{title}</div>
<div style="margin:0;opacity:0.9;font-size:1rem;color:white;">{subtitle}</div>
</div>""",
        unsafe_allow_html=True,
    )


def stat_card(icon: str, value: str | int, label: str):
    """Renderiza um mini card de estatística."""
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-icon">{icon}</div>
            <div class="stat-value">{value}</div>
            <div class="stat-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def chips(items: list[str]):
    """Renderiza uma lista de chips visuais."""
    if not items:
        return
    chips_html = "".join(f'<span class="chip">🏷️ {html.escape(str(item))}</span>' for item in items)
    st.markdown(f'<div style="margin: 0.3rem 0;">{chips_html}</div>', unsafe_allow_html=True)


def status_badge(status: str, text: str = ""):
    """Retorna HTML de um badge de status."""
    display = text or status.capitalize()
    css_class = {
        "aberto": "badge-open",
        "encerrado": "badge-closed",
        "inscrito": "badge-subscribed",
        "urgente": "badge-urgent",
    }.get(status, "badge-open")
    return f'<span class="badge {css_class}">{display}</span>'


def info_badges(items: list[tuple[str, str]]):
    """Renderiza badges informativos inline. items: [(emoji, texto), ...]"""
    if not items:
        return
    badges_html = "".join(
        f'<span class="info-badge">{emoji} {html.escape(str(text))}</span>'
        for emoji, text in items
    )
    st.markdown(f'<div class="info-row">{badges_html}</div>', unsafe_allow_html=True)


def match_display(porcentagem: int):
    """Renderiza o display de match com barra de progresso colorida."""
    level = "high" if porcentagem >= 75 else "medium" if porcentagem >= 50 else "low"
    st.markdown(
        f"""
        <div style="text-align: center;">
            <div class="match-percent {level}">{porcentagem}%</div>
            <div style="font-size: 0.75rem; color: #64748B; font-weight: 500;">Match</div>
        </div>
        <div class="match-bar-container">
            <div class="match-bar {level}" style="width: {porcentagem}%;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def skill_chips(found: list[str], missing: list[str]):
    """Renderiza chips de habilidades encontradas e faltantes."""
    if not found and not missing:
        return
    markup = ""
    for h in found:
        markup += f'<span class="skill-found">✓ {html.escape(str(h))}</span>'
    for h in missing:
        markup += f'<span class="skill-missing">✗ {html.escape(str(h))}</span>'
    st.markdown(f'<div style="margin: 0.4rem 0;">{markup}</div>', unsafe_allow_html=True)


def section_header(icon: str, title: str):
    """Renderiza um cabeçalho de seção estilizado."""
    st.markdown(
        f"""<div class="section-header">
<span style="font-size:1.4rem;">{icon}</span>
<div style="margin:0;font-size:1.3rem;font-weight:600;color:#1E293B;">{title}</div>
</div>""",
        unsafe_allow_html=True,
    )
