"""
🎯 Caçador de Concursos com IA (V2)
Busca concursos públicos via MCP (PCI Concursos), filtra por profissão
usando Gemini IA e analisa compatibilidade com currículo.
"""
import streamlit as st
import hashlib
import time
import logging
import re

from src.config import setup_logging, get_api_key, carregar_config_diaria, salvar_config_diaria
from src import db, mcp_client, pdf_utils, scheduler
from src.pipeline import PipelineCallbacks, salvar_vagas_no_banco, executar_pente_fino_e_extracao, filtrar_vagas_por_profissao, analisar_curriculo
from src.styles import inject_css, hero, stat_card, chips, status_badge, info_badges, match_display, skill_chips, section_header

# Inicialização
setup_logging()
logger = logging.getLogger(__name__)

# ==========================================
# SENIORIDADE
# ==========================================
# "Qualquer" = buscar sem filtrar por senioridade.
NIVEIS_SENIORIDADE = ["Qualquer", "Júnior", "Pleno", "Sênior", "Estágio/Trainee"]

# Reconhece um sufixo de senioridade já presente no nome da área (ex: "UX Designer (Sênior)").
_SUFIXO_SENIORIDADE = re.compile(
    r"\s*\((?:Júnior|Pleno|Sênior|Estágio/Trainee)\)\s*$", re.IGNORECASE
)


def _base_profissao(prof: str) -> str:
    """Remove qualquer sufixo de senioridade existente, devolvendo só a área."""
    return _SUFIXO_SENIORIDADE.sub("", prof).strip()


def _aplicar_senioridade(prof: str, senioridade: str) -> str:
    """
    Embute a senioridade no nome da área (ex: "UX Designer (Sênior)").
    A senioridade embutida mantém o cache correto: cada nível é uma chave distinta.

    - Nível explícito (Júnior/Pleno/Sênior/...): substitui qualquer nível anterior.
    - "Qualquer": preserva a área como veio — inclusive um nível já embutido numa
      área salva — em vez de removê-lo silenciosamente.
    """
    if senioridade and senioridade != "Qualquer":
        return f"{_base_profissao(prof)} ({senioridade})"
    return prof.strip()


# ==========================================
# HELPERS DE CALLBACK STREAMLIT
# ==========================================
def _criar_callbacks_streamlit() -> PipelineCallbacks:
    """Cria callbacks do pipeline com widgets Streamlit."""
    barra = st.progress(0.0)
    texto_status = st.empty()
    return PipelineCallbacks(
        on_info=lambda msg: st.info(msg),
        on_warning=lambda msg: st.warning(msg),
        on_error=lambda msg: st.error(msg),
        on_progress=barra.progress,
        on_status=lambda msg: texto_status.markdown(msg),
        on_fallback=lambda old, new: st.toast(f"⚠️ Alternando de {old} para {new}..."),
        on_toast=lambda msg: st.toast(msg),
        on_done=lambda: (barra.empty(), texto_status.empty()),
    )


# ==========================================
# BUSCA E AGREGAÇÃO DE VAGAS
# ==========================================
def buscar_concursos_abertos(profissoes: list[str], modo_busca: str,
                              regiao: str = "", cargo: str = "",
                              uf: str = "", cidade: str = "") -> int:
    """
    Busca concursos usando o MCP, salva no banco, e roda o Pente Fino.
    Retorna o total de vagas abertas no banco.
    """
    # 1. Busca dados da API conforme o modo selecionado
    st.info("🔌 Conectando ao PCI Concursos via MCP...")
    try:
        if modo_busca == "cargo":
            vagas_brutas = mcp_client.buscar_por_cargo(cargo, uf)
        elif modo_busca == "cidade":
            vagas_brutas = mcp_client.buscar_por_cidade(uf, cidade)
        else:  # região (padrão)
            vagas_brutas = mcp_client.fetch_concursos(regiao)
    except Exception as e:
        logger.error(f"Erro na conexão MCP: {e}")
        st.error("😕 Não foi possível conectar ao servidor de concursos. Tente novamente em alguns minutos.")
        return 0

    if not vagas_brutas:
        st.warning("O servidor respondeu, mas nenhuma vaga foi encontrada com esses filtros.")
        return 0

    # 2. Salva no banco via pipeline
    cb = _criar_callbacks_streamlit()
    novas, _, _ = salvar_vagas_no_banco(vagas_brutas, cb)
    if novas > 0:
        st.success(f"📥 {novas} editais novos encontrados!")

    # 3. Pente Fino + Extração de texto
    api_key = get_api_key()
    if api_key and profissoes:
        cb = _criar_callbacks_streamlit()
        executar_pente_fino_e_extracao(profissoes, api_key, cb)

    # 4. Conta vagas abertas
    conn = db.get_connection()
    try:
        return len(db.buscar_vagas_abertas(conn))
    finally:
        conn.close()


# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
def main():
    st.set_page_config(
        page_title="Caçador de Concursos IA",
        page_icon="🎯",
        layout="wide",
    )
    inject_css()

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("### ⚙️ Configurações")

        # Mini stats
        try:
            conn_sidebar = db.get_connection()
            try:
                total_vagas = len(db.buscar_todas_vagas(conn_sidebar))
            finally:
                conn_sidebar.close()
        except Exception:
            total_vagas = 0

        if total_vagas > 0:
            stat_card("📊", total_vagas, "vagas no banco")
            st.markdown("")

        if st.button("🗑️ Limpar Banco de Dados"):
            import os
            if os.path.exists(db.DB_PATH):
                os.remove(db.DB_PATH)
                st.success("Banco de dados resetado!")
            else:
                st.warning("O banco já está vazio.")

        if st.button("🧹 Limpar Cache da IA"):
            try:
                conn = db.get_connection()
                try:
                    db.limpar_cache_ia(conn)
                    st.success("Cache da IA apagado! A próxima busca reavaliará as vagas.")
                finally:
                    conn.close()
            except Exception as e:
                st.error(f"Erro ao limpar cache: {e}")

        st.markdown("---")
        st.page_link("pages/1_Banco_de_Dados.py", label="📚 Abrir Banco de Dados", icon="👀")

        # --- BUSCA DIÁRIA AUTOMÁTICA ---
        st.markdown("---")
        st.markdown("### 🤖 Busca Diária Automática")
        cfg_diaria = carregar_config_diaria()
        sistema = scheduler.detectar_sistema()
        hora_cfg = int(cfg_diaria.get("horario", 9))

        if sistema == "desconhecido":
            st.caption("⚠️ Agendamento automático não é suportado neste sistema.")
        else:
            st.caption(f"🖥️ {scheduler.nome_sistema()}")
            ativa_atual = bool(cfg_diaria.get("ativa", False))

            ativa = st.toggle(
                "Ativar busca diária",
                value=ativa_atual,
                help="Liga/desliga o agendamento no sistema. Quando ligada, o robô roda "
                     "sozinho todo dia no horário escolhido e gera um relatório HTML.",
            )

            hora_nova = st.number_input(
                "Horário (h)", min_value=0, max_value=23, value=hora_cfg, step=1,
                disabled=not ativa,
            )

            # Liga/desliga: aplica no agendador do SO + persiste a flag
            if ativa != ativa_atual:
                if ativa:
                    ok, msg = scheduler.instalar_agendamento(int(hora_nova))
                else:
                    ok, msg = scheduler.remover_agendamento()
                salvar_config_diaria({"ativa": ativa, "horario": int(hora_nova)})
                (st.toast if ok else st.warning)(msg)
                st.rerun()

            # Reagendar quando o horário muda (só faz sentido se estiver ativa)
            if ativa and int(hora_nova) != hora_cfg:
                if st.button(f"🔄 Reagendar para {int(hora_nova)}h", width="stretch"):
                    ok, msg = scheduler.instalar_agendamento(int(hora_nova))
                    salvar_config_diaria({"horario": int(hora_nova)})
                    (st.success if ok else st.error)(msg)
                    st.rerun()

            if ativa:
                instalado = scheduler.status_agendamento()
                status_txt = "✅ Ativa e agendada" if instalado else "⚠️ Flag ligada, mas o agendador não confirmou"
                st.caption(f"{status_txt} · {len(cfg_diaria.get('profissoes', []))} áreas")
            else:
                st.caption("Desligada — nenhum relatório automático.")

    # --- HERO HEADER ---
    hero(
        "🎯 Caçador de Concursos com IA",
        "Busca inteligente de concursos públicos via MCP + filtragem e análise de currículo com Gemini.",
        badge="V2 — Model Context Protocol",
    )

    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ Configure a chave GEMINI_API_KEY no arquivo `.streamlit/secrets.toml`.")
        st.stop()

    # --- PROFISSÕES ---
    section_header("🔍", "O que você está buscando?")

    profissoes_salvas = []
    try:
        conn = db.get_connection()
        try:
            profissoes_salvas = db.buscar_profissoes_salvas(conn)
        finally:
            conn.close()
    except Exception:
        pass

    # Um único seletor de senioridade, aplicado a todas as áreas ("Qualquer" = sem senioridade).
    # Fica ao lado do input principal: o multiselect (se houver áreas salvas) ou o campo de novas áreas.
    if profissoes_salvas:
        col_sel, col_sen = st.columns([3, 1])
        with col_sel:
            profissoes_selecionadas = st.multiselect(
                "Selecione áreas que já estão no banco:", options=profissoes_salvas
            )
        with col_sen:
            senioridade = st.selectbox("Senioridade:", NIVEIS_SENIORIDADE)

        novas_profissoes = st.text_input(
            "Adicione novas áreas (separe por vírgula):",
            placeholder="Ex: UX Researcher, Product Designer...",
        )
    else:
        profissoes_selecionadas = []
        col_novas, col_sen = st.columns([3, 1])
        with col_novas:
            novas_profissoes = st.text_input(
                "Adicione novas áreas (separe por vírgula):",
                placeholder="Ex: UX Researcher, Product Designer...",
            )
        with col_sen:
            senioridade = st.selectbox("Senioridade:", NIVEIS_SENIORIDADE)

    # Combina cada área com a senioridade escolhida ("Qualquer" = sem senioridade)
    todas_profissoes = [
        _aplicar_senioridade(p, senioridade) for p in profissoes_selecionadas
    ]
    if novas_profissoes:
        todas_profissoes.extend(
            _aplicar_senioridade(p.strip(), senioridade)
            for p in novas_profissoes.split(",")
            if p.strip()
        )

    # Deduplica mantendo a ordem
    profissoes_unicas = {}
    for p in todas_profissoes:
        chave = p.lower()
        if chave not in profissoes_unicas:
            profissoes_unicas[chave] = p
    todas_profissoes = list(profissoes_unicas.values())

    if todas_profissoes:
        chips(todas_profissoes)

    # --- MODO DE BUSCA ---
    st.markdown("")
    modo_busca = st.radio(
        "📍 Como buscar?",
        ["Por Região", "Por Cargo", "Por Cidade"],
        horizontal=True,
    )

    regiao_api = ""
    cargo_busca = ""
    uf_busca = ""
    cidade_busca = ""

    if modo_busca == "Por Região":
        regioes = ["Todas (Nacional)", "sul", "sudeste", "centro-oeste", "norte", "nordeste"]
        regiao_sel = st.selectbox("Região:", regioes)
        regiao_api = "" if "Todas" in regiao_sel else regiao_sel

    elif modo_busca == "Por Cargo":
        col1, col2 = st.columns([3, 1])
        with col1:
            cargo_busca = st.text_input("Cargo:", placeholder="Ex: analista de sistemas")
        with col2:
            uf_busca = st.text_input("UF (opcional):", placeholder="sp", max_chars=2).lower()

    else:  # Cidade
        col1, col2 = st.columns([3, 1])
        with col1:
            cidade_busca = st.text_input("Cidade:", placeholder="Ex: São Paulo")
        with col2:
            uf_busca = st.text_input("UF:", placeholder="sp", max_chars=2).lower()

    # --- BUSCAR ---
    if "vagas_compativeis" not in st.session_state:
        st.session_state.vagas_compativeis = []

    pode_buscar = todas_profissoes and (
        modo_busca == "Por Região"
        or (modo_busca == "Por Cargo" and cargo_busca)
        or (modo_busca == "Por Cidade" and cidade_busca and uf_busca)
    )

    st.markdown("")
    if st.button("🔍 Buscar Vagas Abertas", type="primary", disabled=not pode_buscar):
        modo = "regiao"
        if modo_busca == "Por Cargo":
            modo = "cargo"
        elif modo_busca == "Por Cidade":
            modo = "cidade"

        total_abertas = buscar_concursos_abertos(
            todas_profissoes, modo,
            regiao=regiao_api, cargo=cargo_busca,
            uf=uf_busca, cidade=cidade_busca,
        )

        if total_abertas > 0:
            st.success(f"📋 {total_abertas} editais abertos. Filtrando com IA...")
            cb = _criar_callbacks_streamlit()
            vagas_filtradas = filtrar_vagas_por_profissao(todas_profissoes, api_key, cb)
            st.session_state.vagas_compativeis = vagas_filtradas
            st.success(f"✅ Filtro concluído! **{len(vagas_filtradas)} vagas** da sua área.")
        else:
            st.warning("Nenhuma vaga encontrada. Tente outros filtros.")

    # --- RESULTADOS ---
    if st.session_state.vagas_compativeis:
        section_header("📋", f"Vagas Encontradas ({len(st.session_state.vagas_compativeis)})")

        for v in st.session_state.vagas_compativeis:
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                with col1:
                    st.markdown(f"**{v['orgao']}**")
                    st.caption(f"{v['cargo'][:150]}...")

                    # Info badges
                    badges = []
                    local = v.get("uf") or v.get("regiao")
                    if local:
                        badges.append(("📍", local.upper()))
                    if v.get("salario"):
                        badges.append(("💰", v["salario"]))
                    dias = v.get("dias_restantes", 0)
                    if dias and isinstance(dias, int):
                        if dias > 0:
                            badges.append(("⏰", f"{dias} dias restantes"))
                        elif dias == 0:
                            badges.append(("⚠️", "Último dia!"))
                    datas_texto = v.get("datas_texto", "")
                    if datas_texto:
                        badges.append(("📌", datas_texto))
                    info_badges(badges)

                with col2:
                    # Status badges
                    badges_html = ""
                    if dias and isinstance(dias, int) and 0 <= dias <= 3:
                        badges_html += status_badge("urgente", f"⏰ {dias}d restantes")
                    else:
                        badges_html += status_badge("aberto", "✓ Aberto")
                    st.markdown(badges_html, unsafe_allow_html=True)

        # --- CURRÍCULO ---
        section_header("📄", "Analisar Currículo")

        conn = db.get_connection()
        try:
            cvs_salvos = db.buscar_curriculos(conn)
        finally:
            conn.close()

        opcoes_cv = ["📁 Fazer upload de um novo currículo"]
        dict_cvs = {}
        for row in cvs_salvos:
            label = f"📄 {row[1]} (Enviado em {row[2]})"
            opcoes_cv.append(label)
            dict_cvs[label] = {"hash": row[0], "texto": row[3]}

        escolha_cv = st.selectbox("Escolha um currículo salvo ou envie um novo:", opcoes_cv)

        texto_cv = None

        if escolha_cv == opcoes_cv[0]:
            arquivo_pdf = st.file_uploader("Envie seu currículo (PDF)", type=["pdf"])
            if arquivo_pdf:
                texto_extraido = pdf_utils.extrair_texto_pdf(arquivo_pdf)
                if len(texto_extraido.strip()) < 50:
                    st.error("Não consegui extrair texto suficiente do PDF. Tem certeza que não é uma imagem?")
                else:
                    texto_cv = texto_extraido
                    cv_hash = hashlib.sha256(texto_cv.encode("utf-8")).hexdigest()[:32]
                    data_atual = time.strftime("%d/%m/%Y às %H:%M")

                    conn = db.get_connection()
                    try:
                        db.salvar_curriculo(conn, cv_hash, arquivo_pdf.name, data_atual, texto_cv)
                    finally:
                        conn.close()
        else:
            texto_cv = dict_cvs[escolha_cv]["texto"]

        if texto_cv and st.button("📊 Calcular Compatibilidade", type="primary"):
            with st.spinner("Lendo currículo e cruzando dados..."):
                cb = _criar_callbacks_streamlit()
                ranking = analisar_curriculo(texto_cv, st.session_state.vagas_compativeis, api_key, cb)

                section_header("🏆", "Ranking de Compatibilidade")

                for item in ranking:
                    porcentagem = item.get("porcentagem", 0)

                    with st.container(border=True):
                        col1, col2 = st.columns([4, 1])

                        with col1:
                            st.markdown(f"#### {item['orgao']}")

                            # Info badges
                            row_badges = []
                            local = item.get("uf") or item.get("regiao")
                            if local:
                                row_badges.append(("📍", local.upper()))
                            if item.get("salario"):
                                row_badges.append(("💰", item["salario"]))
                            info_badges(row_badges)

                            st.caption(f"**Cargo(s):** {item['cargo'][:200]}")
                            st.markdown(f"**Por que?** {item.get('justificativa', '')}")

                        with col2:
                            match_display(porcentagem)

                        # Skill chips
                        hab_enc = item.get("habilidades_encontradas", [])
                        hab_falt = item.get("habilidades_faltantes", [])
                        skill_chips(hab_enc, hab_falt)

                        st.link_button("📄 Acessar Edital Oficial", item["link"])


if __name__ == "__main__":
    main()