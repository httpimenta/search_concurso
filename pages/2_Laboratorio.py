"""
🔬 Laboratório de Testes e Diagnóstico
Central unificada para testar extração de currículo, explorar dados da API
e verificar modelos disponíveis do Gemini.
"""
import streamlit as st
import os
import json
import fitz
import pymupdf4llm

from src.config import get_api_key, setup_page_logger, LOG_DIR, MODELOS_CV
from src import ai_engine, mcp_client
from src.styles import inject_css, hero, section_header

st.set_page_config(page_title="Laboratório de Testes", page_icon="🔬", layout="wide")
inject_css()

# Loggers independentes
logger_ats = setup_page_logger("ATS", os.path.join(LOG_DIR, "laboratorio_ats.log"))
logger_mcp = setup_page_logger("MCP", os.path.join(LOG_DIR, "laboratorio_mcp.log"))
logger_modelos = setup_page_logger("Modelos", os.path.join(LOG_DIR, "laboratorio_modelos.log"))

hero(
    "🔬 Laboratório de Testes e Diagnóstico",
    "Central unificada para testar a extração do seu currículo, inspecionar dados da API e conferir os modelos do Gemini.",
    badge="Dev Tools",
)

# Validação da API key
api_key = get_api_key()
if not api_key:
    st.error("⚠️ Chave de API não configurada. Defina GEMINI_API_KEY no secrets.toml.")
    st.stop()

client = ai_engine.get_client(api_key)

tab_cv, tab_mcp, tab_modelos = st.tabs(
    ["📄 ATS Currículo", "🕵️ Explorador MCP", "🤖 Modelos Gemini"]
)

# ==========================================
# TAB 1: DIAGNÓSTICO DE CURRÍCULO
# ==========================================
with tab_cv:
    section_header("📄", "Diagnóstico de Currículo (Visão do ATS)")
    st.markdown(
        "Veja exatamente como a biblioteca extrai o texto do seu PDF e descubra "
        "o que a IA entende dele. Excelente para validar se seu layout é ATS-Friendly."
    )

    arquivo_pdf = st.file_uploader("Faça o upload do Currículo (PDF)", type=["pdf"], key="cv_lab")

    if arquivo_pdf and st.button("🔍 Extrair e Simular Leitura do ATS", type="primary"):
        with st.spinner("Convertendo PDF e enviando para a IA de Diagnóstico..."):
            logger_ats.info(f"Conversão do PDF: {arquivo_pdf.name}")
            try:
                doc = fitz.open(stream=arquivo_pdf.getvalue(), filetype="pdf")
                texto_md = pymupdf4llm.to_markdown(doc)
                logger_ats.info("Conversão PDF → Markdown concluída.")
            except Exception as e:
                logger_ats.error(f"Erro na conversão do PDF: {e}")
                st.error(f"Erro ao ler o arquivo PDF: {e}")
                st.stop()

            col1, col2 = st.columns(2)
            with col1:
                with st.container(border=True):
                    st.markdown("#### 1. Texto Bruto (Visão do Robô)")
                    st.caption("É **exatamente isto** que a IA recebe (Markdown):")
                    st.text_area(
                        "Se as tabelas ou datas estiverem misturadas, o layout quebrou o fluxo de leitura.",
                        texto_md,
                        height=500,
                    )

            with col2:
                with st.container(border=True):
                    st.markdown("#### 2. Interpretação da IA")
                    prompt = f"""
                    Você é um sistema ATS extremamente rigoroso.
                    Analise o currículo em Markdown abaixo:

                    1. **Dados Básicos**: Nome e contato encontrados?
                    2. **Hard Skills**: Principais habilidades técnicas.
                    3. **Qualidade da Conversão**: O Markdown quebrou algo? Datas associadas corretamente?
                    4. **ATS-Score**: Nota 0-10 para o quão ATS-Friendly está.

                    Currículo:
                    ---
                    {texto_md}
                    """

                    try:
                        resposta = ai_engine.chamar_gemini_com_retry(
                            client, prompt, MODELOS_CV,
                            parse_json=False,
                            on_fallback=lambda old, new: st.toast(f"⚠️ Alternando de {old} para {new}..."),
                        )
                        logger_ats.info("Avaliação da IA recebida.")
                        st.markdown(resposta)
                    except RuntimeError as e:
                        logger_ats.error(f"Todos os modelos falharam: {e}")
                        st.error("🚨 Todos os modelos de IA estão indisponíveis no momento. Tente mais tarde.")

# ==========================================
# TAB 2: EXPLORADOR MCP
# ==========================================
with tab_mcp:
    section_header("🕵️", "Explorador de Dados Brutos (MCP)")

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        with st.container(border=True):
            st.markdown("#### 1. Inspecionar Servidor")
            if st.button("🔍 Buscar Ferramentas Disponíveis (tools/list)"):
                with st.spinner("Consultando servidor..."):
                    try:
                        import requests
                        from src.config import MCP_BASE_URL, USER_AGENT
                        headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
                        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                        logger_mcp.info("Enviando POST (tools/list)...")
                        res = requests.post(MCP_BASE_URL, headers=headers, json=payload, timeout=10)
                        logger_mcp.info("Resposta recebida.")
                        st.json(res.json())
                    except Exception as e:
                        logger_mcp.error(f"Erro: {e}")
                        st.error(f"Erro: {e}")

    with col_m2:
        with st.container(border=True):
            st.markdown("#### 2. Extração Completa")
            funcao_mcp = st.radio(
                "🛠️ Ferramenta MCP:",
                ["listar_concursos", "pesquisar_concursos", "buscar_por_cargo", "buscar_por_cidade"],
                horizontal=True,
                key="mcp_radio",
            )

            params_dict: dict = {}
            if funcao_mcp == "listar_concursos":
                regiao = st.selectbox(
                    "📍 Região (Opcional):",
                    ["", "sul", "sudeste", "centro-oeste", "norte", "nordeste"],
                    key="mcp_regiao",
                )
                if regiao:
                    params_dict["regiao"] = regiao

            elif funcao_mcp == "pesquisar_concursos":
                termo = st.text_input("🔑 Termo de busca:", key="mcp_termo")
                uf = st.text_input("📍 UF (Opcional):", max_chars=2, key="mcp_uf").lower()
                if termo:
                    params_dict["termo"] = termo
                if uf:
                    params_dict["uf"] = uf

            elif funcao_mcp == "buscar_por_cargo":
                cargo = st.text_input("🔑 Cargo:", key="mcp_cargo")
                uf = st.text_input("📍 UF (Opcional):", max_chars=2, key="mcp_cargo_uf").lower()
                if cargo:
                    params_dict["cargo"] = cargo
                if uf:
                    params_dict["uf"] = uf

            elif funcao_mcp == "buscar_por_cidade":
                uf = st.text_input("📍 UF (obrigatório):", max_chars=2, key="mcp_cidade_uf").lower()
                cidade = st.text_input("🏙️ Cidade:", key="mcp_cidade")
                if uf:
                    params_dict["uf"] = uf
                if cidade:
                    params_dict["cidade"] = cidade

            if st.button("📥 Extrair Vagas", type="primary"):
                # Validação
                if funcao_mcp == "pesquisar_concursos" and "termo" not in params_dict:
                    st.error("O campo 'Termo de busca' é obrigatório.")
                elif funcao_mcp == "buscar_por_cargo" and "cargo" not in params_dict:
                    st.error("O campo 'Cargo' é obrigatório.")
                elif funcao_mcp == "buscar_por_cidade" and ("uf" not in params_dict or "cidade" not in params_dict):
                    st.error("Os campos 'UF' e 'Cidade' são obrigatórios.")
                else:
                    with st.spinner("Baixando dados..."):
                        try:
                            import requests
                            from src.config import MCP_BASE_URL, USER_AGENT
                            headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
                            payload = {
                                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                "params": {"name": funcao_mcp, "arguments": params_dict},
                            }
                            logger_mcp.info(f"POST (tools/call - {funcao_mcp})...")
                            res = requests.post(MCP_BASE_URL, headers=headers, json=payload, timeout=15)
                            dados_brutos = res.json()

                            vagas_ex = mcp_client._extrair_data(dados_brutos)

                            logger_mcp.info(f"Extração: {len(vagas_ex)} vagas.")
                            st.session_state.vagas_mcp = vagas_ex
                            st.session_state.dados_mcp_raw = dados_brutos
                            st.success(f"Foram encontradas {len(vagas_ex)} vagas!")
                        except Exception as e:
                            logger_mcp.error(f"Erro: {e}")
                            st.error(f"Erro ao extrair: {e}")

    if st.session_state.get("vagas_mcp"):
        st.markdown("")
        section_header("📊", "Resultados da Extração")
        visao = st.radio(
            "Selecione como investigar os dados:",
            ["📊 Raio-X de Tags", "📋 Tabela Interativa", "🧩 JSON Bruto Completo"],
            horizontal=True,
        )
        vagas = st.session_state.vagas_mcp

        if "Tags" in visao:
            todas_chaves: set[str] = set()
            for v in vagas:
                if isinstance(v, dict):
                    todas_chaves.update(v.keys())
            for chave in sorted(todas_chaves):
                tipos = {type(v.get(chave)).__name__ for v in vagas if isinstance(v, dict) and v.get(chave) is not None}
                amostras = [str(v.get(chave)) for v in vagas if isinstance(v, dict) and v.get(chave) is not None][:3]
                with st.expander(f"🏷️ Tag: {chave} | Tipos: {', '.join(tipos)}"):
                    for am in amostras:
                        st.code(am, language="text")

        elif "Tabela" in visao:
            vagas_tab = [
                {k: str(v) if isinstance(v, (dict, list)) else v for k, v in item.items()}
                for item in vagas
            ]
            st.dataframe(vagas_tab, width="stretch")

        else:
            st.json(st.session_state.dados_mcp_raw)

# ==========================================
# TAB 3: MODELOS DA API
# ==========================================
with tab_modelos:
    section_header("🤖", "Explorador de Modelos da API (Google Gemini)")
    if st.button("🔍 Listar Modelos Disponíveis na Minha Conta", type="primary"):
        with st.spinner("Consultando servidores..."):
            try:
                logger_modelos.info("Consultando lista de modelos...")
                modelos = client.models.list()
                lista_exp = []
                for m in modelos:
                    nm = getattr(m, "name", "").replace("models/", "")
                    detalhes = {
                        "nome_interno": nm,
                        "nome_exibicao": getattr(m, "display_name", nm),
                        "descricao": getattr(m, "description", "N/A"),
                        "limite_tokens_entrada": getattr(m, "input_token_limit", "N/A"),
                        "limite_tokens_saida": getattr(m, "output_token_limit", "N/A"),
                    }
                    lista_exp.append(detalhes)
                    with st.expander(f"✅ {detalhes['nome_exibicao']}"):
                        st.code(detalhes["nome_interno"], language="python")
                        st.write(f"**Descrição:** {detalhes['descricao']}")
                        st.write(f"**Tokens (In/Out):** {detalhes['limite_tokens_entrada']} / {detalhes['limite_tokens_saida']}")

                logger_modelos.info(f"Consulta: {len(lista_exp)} modelos.")
                st.download_button(
                    "📥 Exportar Detalhes (JSON)",
                    json.dumps(lista_exp, ensure_ascii=False, indent=2),
                    "modelos_api.json",
                    "application/json",
                    width="stretch",
                )
            except Exception as e:
                logger_modelos.error(f"Erro: {e}")
                st.error(f"Erro: {e}")