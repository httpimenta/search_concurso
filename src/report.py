"""
Gerador de relatório HTML rico para o Caçador de Concursos IA.
Produz um arquivo HTML standalone, dark mode, com todas as vagas encontradas.
"""
from __future__ import annotations
import html
from datetime import datetime


def _esc(valor, quote: bool = False) -> str:
    """Escapa um valor para inserção segura em HTML (dados da API/IA são não confiáveis)."""
    return html.escape(str(valor or ""), quote=quote)


def _format_date(iso_str: str) -> str:
    """Formata data ISO para dd/mm/aaaa."""
    if not iso_str:
        return "Não informada"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def gerar_relatorio_html(
    vagas_compativeis: list[dict],
    ranking_cv: list[dict] | None,
    profissoes: list[str],
    timestamp: str,
    total_brutas: int = 0,
    total_abertas: int = 0,
    novas: int = 0,
) -> str:
    """
    Gera um relatório HTML completo e auto-contido com os resultados da busca diária.

    Args:
        vagas_compativeis: Vagas filtradas pela IA como compatíveis
        ranking_cv: Ranking de compatibilidade com currículo (None se não analisou)
        profissoes: Lista de profissões buscadas
        timestamp: Timestamp da execução (string formatada)
        total_brutas: Total de vagas brutas encontradas
        total_abertas: Total de vagas abertas no banco
        novas: Número de vagas novas encontradas nesta execução
    """

    # ── Seção de vagas compatíveis ──
    vagas_html = ""
    if vagas_compativeis:
        for vaga in vagas_compativeis:
            dias = vaga.get("dias_restantes", 0) or 0
            urgencia_class = ""
            urgencia_badge = ""
            if isinstance(dias, int):
                if 0 <= dias <= 3:
                    urgencia_class = "urgente"
                    urgencia_badge = f'<span class="badge urgente">⏰ {dias}d restantes</span>'
                elif dias > 0:
                    urgencia_badge = f'<span class="badge aberto">✓ {dias}d restantes</span>'
                else:
                    urgencia_badge = '<span class="badge aberto">✓ Aberto</span>'
            else:
                urgencia_badge = '<span class="badge aberto">✓ Aberto</span>'

            datas_texto = vaga.get("datas_texto", "")
            local = (vaga.get("uf") or vaga.get("regiao") or "").upper()
            salario = vaga.get("salario", "")
            link = _esc(vaga.get("link", "#"), quote=True)

            meta_items = []
            if local:
                meta_items.append(f'<span class="meta-item">📍 {_esc(local)}</span>')
            if salario:
                meta_items.append(f'<span class="meta-item">💰 {_esc(salario)}</span>')
            if datas_texto:
                meta_items.append(f'<span class="meta-item">📌 {_esc(datas_texto)}</span>')

            vagas_html += f"""
            <div class="job-card {urgencia_class}">
                <div class="job-header">
                    <h3><a href="{link}" target="_blank">{_esc(vaga.get('orgao', 'Órgão'))}</a></h3>
                    {urgencia_badge}
                </div>
                <p class="job-cargo">{_esc((vaga.get('cargo', '') or '')[:200])}</p>
                <div class="job-meta">{''.join(meta_items)}</div>
                <a href="{link}" target="_blank" class="btn-edital">📄 Ver Edital →</a>
            </div>
            """
    else:
        vagas_html = """
        <div class="no-results">
            <div class="no-results-icon">🔍</div>
            <h2>Nenhuma vaga compatível encontrada hoje</h2>
            <p>A IA não encontrou vagas abertas compatíveis com suas profissões nesta busca.</p>
        </div>
        """

    # ── Seção de ranking de currículo ──
    ranking_html = ""
    if ranking_cv:
        ranking_html = '<div class="section"><h2 class="section-title">🏆 Ranking de Compatibilidade com Currículo</h2>'
        for item in ranking_cv:
            pct = item.get("porcentagem", 0)
            if pct >= 70:
                pct_class = "match-high"
            elif pct >= 40:
                pct_class = "match-mid"
            else:
                pct_class = "match-low"

            hab_enc = item.get("habilidades_encontradas", [])
            hab_falt = item.get("habilidades_faltantes", [])

            skills_html = ""
            if hab_enc:
                chips = "".join(f'<span class="chip found">✓ {_esc(h)}</span>' for h in hab_enc)
                skills_html += f'<div class="skills-row">{chips}</div>'
            if hab_falt:
                chips = "".join(f'<span class="chip missing">✗ {_esc(h)}</span>' for h in hab_falt)
                skills_html += f'<div class="skills-row">{chips}</div>'

            local = (item.get("uf") or item.get("regiao") or "").upper()
            link = _esc(item.get("link", "#"), quote=True)

            ranking_html += f"""
            <div class="ranking-card">
                <div class="ranking-header">
                    <div class="ranking-info">
                        <h3><a href="{link}" target="_blank">{_esc(item.get('orgao', ''))}</a></h3>
                        <p class="job-cargo">{_esc((item.get('cargo', '') or '')[:200])}</p>
                        {'<span class="meta-item">📍 ' + _esc(local) + '</span>' if local else ''}
                    </div>
                    <div class="match-circle {pct_class}">
                        <span class="match-number">{pct}%</span>
                    </div>
                </div>
                <p class="justificativa">{_esc(item.get('justificativa', ''))}</p>
                {skills_html}
                <a href="{link}" target="_blank" class="btn-edital">📄 Ver Edital →</a>
            </div>
            """
        ranking_html += "</div>"

    # ── Profissões pills ──
    profissoes_pills = "".join(
        f'<span class="prof-pill">{_esc(p)}</span>' for p in profissoes
    )

    # ── HTML completo ──
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎯 Caçador de Concursos — {timestamp}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --accent: #6C5CE7;
            --accent-soft: rgba(108, 92, 231, 0.15);
            --accent-glow: rgba(108, 92, 231, 0.3);
            --success: #00B894;
            --warning: #FDCB6E;
            --danger: #E17055;
            --bg: #0D0D12;
            --bg-card: #16161F;
            --bg-card-hover: #1E1E2A;
            --text: #F0F0F5;
            --text-secondary: #9B9BB0;
            --text-muted: #5B5B70;
            --border: #252535;
            --glass: rgba(22, 22, 31, 0.85);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            line-height: 1.6;
        }}

        /* ── Hero ── */
        .hero {{
            background: linear-gradient(135deg, #0d0a1a 0%, var(--bg) 40%, #1a0d15 100%);
            border-bottom: 1px solid var(--border);
            padding: 3rem 2rem 2rem;
            position: relative;
            overflow: hidden;
        }}
        .hero::before {{
            content: '';
            position: absolute;
            top: -50%; left: -50%;
            width: 200%; height: 200%;
            background: radial-gradient(circle at 30% 50%, rgba(108,92,231,0.08) 0%, transparent 50%),
                        radial-gradient(circle at 70% 80%, rgba(0,184,148,0.05) 0%, transparent 50%);
            animation: glow 15s ease-in-out infinite;
        }}
        @keyframes glow {{
            0%, 100% {{ transform: translate(0, 0); }}
            50% {{ transform: translate(-2%, 1%); }}
        }}
        .hero-content {{
            max-width: 1200px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }}
        .hero-top {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }}
        .hero-logo {{ font-size: 2.5rem; }}
        .hero h1 {{
            font-size: 2rem; font-weight: 800;
            background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .hero-subtitle {{ color: var(--text-secondary); font-size: 0.95rem; margin-top: 0.25rem; }}
        .hero-timestamp {{ color: var(--text-muted); font-size: 0.8rem; margin-top: 0.5rem; }}

        /* ── Stats ── */
        .stats-row {{
            display: flex; gap: 1.5rem; flex-wrap: wrap; margin-top: 1.5rem;
        }}
        .stat {{
            background: var(--glass);
            border: 1px solid var(--border);
            border-radius: 16px; padding: 1.25rem 1.75rem;
            backdrop-filter: blur(20px); min-width: 130px;
            transition: transform 0.2s, border-color 0.2s;
        }}
        .stat:hover {{ transform: translateY(-2px); border-color: var(--accent-glow); }}
        .stat-num {{ font-size: 2rem; font-weight: 800; color: var(--accent); line-height: 1; }}
        .stat-label {{
            font-size: 0.75rem; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.25rem;
        }}

        /* ── Profissões ── */
        .prof-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }}
        .prof-pill {{
            background: var(--accent-soft); color: var(--accent);
            border: 1px solid var(--accent-glow); border-radius: 100px;
            padding: 0.3rem 0.8rem; font-size: 0.8rem; font-weight: 500;
        }}

        /* ── Main ── */
        .main {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}

        /* ── Section ── */
        .section {{ margin-bottom: 3rem; }}
        .section-title {{
            font-size: 1.3rem; font-weight: 700; margin-bottom: 1.25rem;
            padding-bottom: 0.75rem; border-bottom: 1px solid var(--border);
        }}

        /* ── Job Cards ── */
        .jobs-grid {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1rem;
        }}
        .job-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px; padding: 1.25rem;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex; flex-direction: column; gap: 0.6rem;
            border-left: 3px solid var(--accent);
        }}
        .job-card:hover {{
            background: var(--bg-card-hover);
            transform: translateY(-3px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.3);
        }}
        .job-card.urgente {{ border-left-color: var(--danger); }}
        .job-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; }}
        .job-header h3 {{ font-size: 1rem; font-weight: 600; flex: 1; }}
        .job-header h3 a {{ color: var(--text); text-decoration: none; transition: color 0.2s; }}
        .job-header h3 a:hover {{ color: var(--accent); }}
        .job-cargo {{ font-size: 0.85rem; color: var(--text-secondary); line-height: 1.4; }}
        .job-meta {{ display: flex; flex-wrap: wrap; gap: 0.75rem; }}
        .meta-item {{ font-size: 0.8rem; color: var(--text-secondary); }}

        .badge {{
            font-size: 0.7rem; font-weight: 700; padding: 0.2rem 0.6rem;
            border-radius: 6px; text-transform: uppercase; white-space: nowrap;
        }}
        .badge.aberto {{ background: rgba(0,184,148,0.12); color: #55EFC4; }}
        .badge.urgente {{
            background: rgba(225,112,85,0.15); color: #FF7675;
            animation: pulse 2s ease-in-out infinite;
        }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.6; }} }}

        .btn-edital {{
            display: inline-flex; align-items: center; justify-content: center;
            background: var(--accent); color: white;
            padding: 0.5rem 1rem; border-radius: 8px;
            font-size: 0.8rem; font-weight: 600;
            text-decoration: none; transition: all 0.2s;
            margin-top: auto;
        }}
        .btn-edital:hover {{ filter: brightness(1.15); transform: translateY(-1px); }}

        /* ── Ranking ── */
        .ranking-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px; padding: 1.5rem;
            margin-bottom: 1rem;
            transition: all 0.25s;
        }}
        .ranking-card:hover {{
            background: var(--bg-card-hover);
            border-color: var(--accent-glow);
        }}
        .ranking-header {{
            display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;
        }}
        .ranking-info {{ flex: 1; }}
        .ranking-info h3 {{ font-size: 1rem; font-weight: 600; }}
        .ranking-info h3 a {{ color: var(--text); text-decoration: none; }}
        .ranking-info h3 a:hover {{ color: var(--accent); }}

        .match-circle {{
            width: 70px; height: 70px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0; border: 3px solid;
        }}
        .match-circle.match-high {{ border-color: var(--success); background: rgba(0,184,148,0.1); }}
        .match-circle.match-mid {{ border-color: var(--warning); background: rgba(253,203,110,0.1); }}
        .match-circle.match-low {{ border-color: var(--danger); background: rgba(225,112,85,0.1); }}
        .match-number {{ font-size: 1.1rem; font-weight: 800; }}
        .match-high .match-number {{ color: var(--success); }}
        .match-mid .match-number {{ color: var(--warning); }}
        .match-low .match-number {{ color: var(--danger); }}

        .justificativa {{
            font-size: 0.85rem; color: var(--text-secondary);
            margin: 0.75rem 0; line-height: 1.5; font-style: italic;
        }}
        .skills-row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.5rem; }}
        .chip {{
            font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.6rem;
            border-radius: 6px;
        }}
        .chip.found {{ background: rgba(0,184,148,0.12); color: #55EFC4; }}
        .chip.missing {{ background: rgba(225,112,85,0.12); color: #FF7675; }}

        /* ── No results ── */
        .no-results {{
            text-align: center; padding: 3rem 1rem;
            color: var(--text-muted);
        }}
        .no-results-icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        .no-results h2 {{ font-size: 1.2rem; font-weight: 600; color: var(--text-secondary); }}

        /* ── Footer ── */
        .footer {{
            text-align: center; padding: 2rem;
            color: var(--text-muted); font-size: 0.75rem;
            border-top: 1px solid var(--border); margin-top: 3rem;
        }}

        /* ── Responsivo ── */
        @media (max-width: 768px) {{
            .hero {{ padding: 2rem 1rem 1.5rem; }}
            .hero h1 {{ font-size: 1.5rem; }}
            .stats-row {{ gap: 0.75rem; }}
            .stat {{ min-width: 100px; padding: 1rem; }}
            .stat-num {{ font-size: 1.5rem; }}
            .jobs-grid {{ grid-template-columns: 1fr; }}
            .main {{ padding: 1rem; }}
            .ranking-header {{ flex-direction: column; }}
            .match-circle {{ align-self: flex-end; }}
        }}
    </style>
</head>
<body>

<div class="hero">
    <div class="hero-content">
        <div class="hero-top">
            <span class="hero-logo">🎯</span>
            <div>
                <h1>Caçador de Concursos — Relatório Diário</h1>
                <p class="hero-subtitle">Busca automatizada de concursos públicos com filtragem inteligente por IA</p>
                <p class="hero-timestamp">Gerado em {timestamp}</p>
            </div>
        </div>

        <div class="stats-row">
            <div class="stat">
                <div class="stat-num">{total_brutas}</div>
                <div class="stat-label">Vagas Brutas</div>
            </div>
            <div class="stat">
                <div class="stat-num">{total_abertas}</div>
                <div class="stat-label">Abertas no Banco</div>
            </div>
            <div class="stat">
                <div class="stat-num">{len(vagas_compativeis)}</div>
                <div class="stat-label">Compatíveis</div>
            </div>
            <div class="stat">
                <div class="stat-num">{novas}</div>
                <div class="stat-label">Novas Hoje</div>
            </div>
            {f'<div class="stat"><div class="stat-num">{len(ranking_cv)}</div><div class="stat-label">Com CV</div></div>' if ranking_cv else ''}
        </div>

        <div class="prof-row">
            {profissoes_pills}
        </div>
    </div>
</div>

<div class="main">

    <div class="section">
        <h2 class="section-title">📋 Vagas Compatíveis ({len(vagas_compativeis)})</h2>
        <div class="jobs-grid">
            {vagas_html}
        </div>
    </div>

    {ranking_html}

</div>

<div class="footer">
    <p>🎯 Caçador de Concursos IA — Relatório gerado automaticamente em {timestamp}</p>
    <p>Powered by Gemini AI + PCI Concursos MCP</p>
</div>

</body>
</html>"""

    return html
