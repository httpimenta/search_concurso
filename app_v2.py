"""
🎯 Caçador de Concursos com IA (V2)
Busca concursos públicos via MCP (PCI Concursos), filtra por profissão
usando Gemini IA e analisa compatibilidade com currículo.
"""
import streamlit as st
import json
import hashlib
import time
import logging

from src.config import (
    setup_logging, get_api_key,
    MODELOS_PENTE_FINO, MODELOS_FILTRO, MODELOS_CV,
    LOTE_PENTE_FINO, LOTE_FILTRO, LOTE_CV,
)
from src import db, mcp_client, ai_engine, pdf_utils

# Inicialização
setup_logging()
logger = logging.getLogger(__name__)


# ==========================================
# BUSCA E AGREGAÇÃO DE VAGAS
# ==========================================
def buscar_concursos_abertos(profissao_buscada: str, modo_busca: str,
                              regiao: str = "", cargo: str = "",
                              uf: str = "", cidade: str = "") -> list[dict]:
    """
    Busca concursos usando o MCP, salva no banco, e retorna as vagas abertas.
    Suporta 3 modos de busca: região, cargo e cidade.
    """
    conn = db.get_connection()
    try:
        db.migrate(conn)

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
            return []

        if not vagas_brutas:
            st.warning("O servidor respondeu, mas nenhuma vaga foi encontrada com esses filtros.")
            return []

        # 2. Salva no banco
        vagas = mcp_client.parse_vagas(vagas_brutas)
        links_salvos = db.buscar_links_salvos(conn)
        links_ativos = []
        links_encerrados = []
        novos = 0

        for vaga in vagas:
            if not vaga.link:
                continue

            if vaga.datas.aberto:
                links_ativos.append(vaga.link)
            else:
                links_encerrados.append(vaga.link)

            if vaga.link not in links_salvos:
                status = "aberto" if vaga.datas.aberto else "encerrado"
                db.salvar_vaga(
                    conn, vaga.link, vaga.orgao, vaga.cargo,
                    vaga.descricao_resumida, status, vaga.datas.fim,
                    vaga.vagas_salario, vaga.formacao, vaga.regiao, vaga.uf,
                    vaga.datas.dias_restantes, vaga.datas.texto,
                )
                links_salvos.add(vaga.link)
                novos += 1

        conn.commit()

        # 3. Atualiza status
        db.atualizar_status_vagas(conn, links_ativos, links_encerrados)

        if novos > 0:
            st.success(f"📥 {novos} editais novos encontrados!")

        # 4. Pente Fino + Extração de texto
        _executar_pente_fino_e_extracao(conn, profissao_buscada)

        # 5. Retorna vagas abertas
        return db.buscar_vagas_abertas(conn)

    finally:
        conn.close()


def _executar_pente_fino_e_extracao(conn, profissao_buscada: str) -> None:
    """Avalia quais vagas são relevantes e extrai o texto completo das aprovadas."""
    vagas_sem_texto = db.buscar_vagas_sem_texto(conn)
    if not vagas_sem_texto:
        return

    profissoes_lista = [p.strip() for p in profissao_buscada.split(",") if p.strip()]
    if not profissoes_lista:
        profissoes_lista = [profissao_buscada.strip()]

    cache_pente = db.buscar_cache_filtro(conn, profissoes_lista)
    vagas_para_extrair = []
    vagas_para_pente_fino = []

    for vaga in vagas_sem_texto:
        link = vaga["link"]
        link_cache = cache_pente.get(link, {})

        # Já rejeitada para todas as profissões → pula
        if all(p in link_cache and not link_cache[p] for p in profissoes_lista):
            continue

        # Já aprovada para alguma profissão → extrai direto
        if any(link_cache.get(p) is True for p in profissoes_lista):
            vagas_para_extrair.append(vaga)
            continue

        cargo_str = vaga["cargo"].lower()
        if "vários cargos" in cargo_str:
            vagas_para_extrair.append(vaga)
        else:
            vagas_para_pente_fino.append({
                "id": len(vagas_para_pente_fino),
                "cargo": vaga["cargo"],
                "orgao": vaga["orgao"],
                "link": vaga["link"],
            })

    # Pente Fino: avaliação rápida pela IA
    if vagas_para_pente_fino:
        _executar_pente_fino(conn, vagas_para_pente_fino, vagas_sem_texto,
                             vagas_para_extrair, profissoes_lista)

    # Extração paralela de texto das páginas
    if vagas_para_extrair:
        _executar_extracao_texto(conn, vagas_para_extrair)


def _executar_pente_fino(conn, vagas_pente: list, vagas_sem_texto: list,
                          vagas_para_extrair: list, profissoes: list) -> None:
    """Usa a IA para filtrar rapidamente cargos irrelevantes."""
    api_key = get_api_key()
    if not api_key:
        return

    client = ai_engine.get_client(api_key)
    barra = st.progress(0.0)
    texto_status = st.empty()
    total = len(vagas_pente)
    analises_batch = []

    for i_batch in range(0, total, LOTE_PENTE_FINO):
        lote = vagas_pente[i_batch:i_batch + LOTE_PENTE_FINO]
        lote_num = (i_batch // LOTE_PENTE_FINO) + 1
        total_lotes = (total + LOTE_PENTE_FINO - 1) // LOTE_PENTE_FINO

        texto_status.markdown(
            f"**🔎 Pente Fino:** Analisando {total} cargos resumidos... "
            f"(lote {lote_num}/{total_lotes})"
        )

        prompt = f"""
        O candidato atua nas áreas: {profissoes}.
        Avalie se os seguintes cargos de concurso têm ALGUMA chance (mesmo que mínima)
        de englobar as áreas do candidato.

        DIRETRIZES:
        1. APROVE CARGOS GENÉRICOS: Nomes como "Analista de Tecnologia", "Analista de Sistemas",
           "Técnico de Nível Superior", "Especialista" podem esconder vagas relevantes. Na dúvida, retorne true.
        2. REJEITE ESPECIALIDADES DISTINTAS: Não confunda as áreas. Se o candidato é de UX/UI/Product Design,
           NÃO aprove vagas estritamente focadas em "Design Gráfico", "Web Design Clássico", "Publicidade".

        Retorne EXATAMENTE neste formato JSON:
        [ {{"id": 0, "relevante": true}}, {{"id": 1, "relevante": false}} ]

        Cargos:
        {json.dumps([{"id": v["id"], "cargo": v["cargo"], "orgao": v["orgao"]} for v in lote], ensure_ascii=False)}
        """

        try:
            resultados = ai_engine.chamar_gemini_com_retry(client, prompt, MODELOS_PENTE_FINO)
            for res in resultados:
                id_vaga = res.get("id")
                if isinstance(id_vaga, int) and 0 <= id_vaga < len(vagas_pente):
                    link_alvo = vagas_pente[id_vaga]["link"]
                    if res.get("relevante"):
                        vaga_rel = next((v for v in vagas_sem_texto if v["link"] == link_alvo), None)
                        if vaga_rel:
                            vagas_para_extrair.append(vaga_rel)
                    else:
                        for prof in profissoes:
                            analises_batch.append((link_alvo, prof, 0))
        except RuntimeError as e:
            logger.error(f"Pente Fino falhou: {e}")

        barra.progress(min((i_batch + LOTE_PENTE_FINO) / total, 1.0))

    # Commit em lote
    if analises_batch:
        db.salvar_analises_filtro_batch(conn, analises_batch)

    barra.empty()
    texto_status.empty()


def _executar_extracao_texto(conn, vagas: list) -> None:
    """Extrai o texto completo das páginas das vagas relevantes (em paralelo)."""
    # Remove duplicatas
    vagas_unicas = {v["link"]: v for v in vagas}
    urls = list(vagas_unicas.keys())
    total = len(urls)

    barra = st.progress(0.0)
    texto_status = st.empty()
    texto_status.markdown(f"**⏳ Extraindo texto de {total} editais relevantes...**")

    resultados = mcp_client.extrair_texto_paginas_paralelo(urls, max_workers=5)

    for i, (url, texto) in enumerate(resultados.items()):
        db.marcar_texto_extraido(conn, url, texto)
        barra.progress((i + 1) / total)

    conn.commit()
    barra.empty()
    texto_status.empty()


# ==========================================
# FILTRO DETALHADO POR PROFISSÃO
# ==========================================
def filtrar_vagas_por_profissao(profissao_buscada: str, vagas: list[dict]) -> list[dict]:
    """Usa a IA para determinar quais vagas são compatíveis com as profissões do candidato."""
    if not vagas:
        return []

    conn = db.get_connection()
    try:
        db.migrate(conn)
        profissoes_lista = [p.strip() for p in profissao_buscada.split(",") if p.strip()]
        if not profissoes_lista:
            profissoes_lista = [profissao_buscada.strip()]

        cache = db.buscar_cache_filtro(conn, profissoes_lista)
        vagas_compativeis = []
        vagas_para_analisar = []

        for vaga in vagas:
            link = vaga["link"]
            link_cache = cache.get(link, {})

            if any(link_cache.get(p) is True for p in profissoes_lista):
                vagas_compativeis.append(vaga)
            elif all(p in link_cache and not link_cache[p] for p in profissoes_lista):
                pass  # Já rejeitada
            else:
                vagas_para_analisar.append(vaga)

        if not vagas_para_analisar:
            st.toast("⚡ Histórico carregado do banco de dados (0 novas vagas para processar)!")
            return vagas_compativeis

        st.info(f"🤖 Analisando {len(vagas_para_analisar)} vagas inéditas com IA...")

        api_key = get_api_key()
        if not api_key:
            return vagas_compativeis

        client = ai_engine.get_client(api_key)
        total_lotes = (len(vagas_para_analisar) + LOTE_FILTRO - 1) // LOTE_FILTRO
        barra = st.progress(0.0)
        texto_status = st.empty()

        for i in range(0, len(vagas_para_analisar), LOTE_FILTRO):
            lote_num = (i // LOTE_FILTRO) + 1
            lote = vagas_para_analisar[i:i + LOTE_FILTRO]

            texto_status.markdown(
                f"**🤖 IA analisando editais: lote {lote_num}/{total_lotes}**"
            )

            vagas_simplificadas = [
                {"id": i + j, "cargo": v["cargo"], "descricao": v["descricao_resumida"]}
                for j, v in enumerate(lote)
            ]

            prompt = f"""
            Você é um recrutador especialista. O candidato atua nas seguintes áreas: {profissoes_lista}.
            Muitas vezes o nome oficial do cargo não reflete a profissão exata,
            mas as atividades descritas no edital são exatamente o que o candidato faz.

            Determine se cada vaga é compatível com ALGUMA das áreas do candidato.
            Se for compatível, liste quais áreas exatas dão match.

            Retorne no formato JSON:
            [ {{"id": 0, "compativel": true, "profissoes_match": ["Service Designer"]}},
              {{"id": 1, "compativel": false, "profissoes_match": []}} ]

            Vagas:
            {json.dumps(vagas_simplificadas, ensure_ascii=False)}
            """

            try:
                resultados = ai_engine.chamar_gemini_com_retry(
                    client, prompt, MODELOS_FILTRO,
                    on_fallback=lambda old, new: st.toast(f"⚠️ Alternando de {old} para {new}..."),
                )

                analises_batch = []
                for res in resultados:
                    id_vaga = res.get("id")
                    if not isinstance(id_vaga, int) or id_vaga < 0 or id_vaga >= len(vagas_para_analisar):
                        continue

                    compativel = res.get("compativel") is True
                    profissoes_match = [str(p).lower().strip() for p in res.get("profissoes_match", [])]
                    vaga_original = vagas_para_analisar[id_vaga]

                    for prof in profissoes_lista:
                        is_match = 1 if compativel and (
                            prof.lower() in profissoes_match or len(profissoes_lista) == 1
                        ) else 0
                        analises_batch.append((vaga_original["link"], prof, is_match))

                    if compativel:
                        vagas_compativeis.append(vaga_original)

                # Commit em lote (fix: antes era dentro do loop)
                db.salvar_analises_filtro_batch(conn, analises_batch)

            except RuntimeError as e:
                logger.error(f"Filtro detalhado falhou: {e}")
                st.toast("⚠️ Erro ao analisar com IA. Alguns editais podem ter sido ignorados.")

            if i + LOTE_FILTRO < len(vagas_para_analisar):
                time.sleep(MODELOS_FILTRO[0]["pausa"])

            barra.progress(lote_num / total_lotes)

        barra.empty()
        texto_status.empty()
        return vagas_compativeis

    finally:
        conn.close()


# ==========================================
# ANÁLISE DE CURRÍCULO
# ==========================================
def calcular_compatibilidade_curriculo(texto_curriculo: str, vagas: list[dict]) -> list[dict]:
    """Cruza o currículo com cada vaga, dando uma porcentagem de compatibilidade."""
    if not vagas:
        return []

    cv_hash = hashlib.md5(texto_curriculo.encode("utf-8")).hexdigest()

    conn = db.get_connection()
    try:
        db.migrate(conn)

        links_vagas = [v["link"] for v in vagas]
        cache_cv = db.buscar_cache_cv(conn, cv_hash, links_vagas)

        resultados = []
        vagas_para_analisar = []

        for vaga in vagas:
            link = vaga["link"]
            if link in cache_cv:
                vaga_cacheada = vaga.copy()
                vaga_cacheada.update(cache_cv[link])
                resultados.append(vaga_cacheada)
            else:
                vagas_para_analisar.append(vaga)

        if not vagas_para_analisar:
            st.toast("⚡ Resultados resgatados do cache! (0 requisições novas à API)")
            return sorted(resultados, key=lambda x: x["porcentagem"], reverse=True)

        st.info(f"🔬 Analisando {len(vagas_para_analisar)} editais com seu currículo...")

        api_key = get_api_key()
        if not api_key:
            return sorted(resultados, key=lambda x: x.get("porcentagem", 0), reverse=True)

        client = ai_engine.get_client(api_key)
        total_lotes = (len(vagas_para_analisar) + LOTE_CV - 1) // LOTE_CV
        barra = st.progress(0.0)
        texto_status = st.empty()

        # System instruction com o currículo (enviado uma vez, não repetido a cada lote)
        system_cv = f"Você é um avançado sistema de ATS. Abaixo está o currículo do candidato:\n---\n{texto_curriculo}\n---"

        for i_batch in range(0, len(vagas_para_analisar), LOTE_CV):
            lote_num = (i_batch // LOTE_CV) + 1
            lote = vagas_para_analisar[i_batch:i_batch + LOTE_CV]

            texto_status.markdown(
                f"**🔬 Baixando e analisando PDFs (Lote {lote_num}/{total_lotes})**"
            )

            prompt = "Analise os EDITAIS OFICIAIS das seguintes vagas:\n"
            for j, vaga in enumerate(lote):
                texto_edital = pdf_utils.extrair_texto_edital_pdf(vaga["link"], conn)
                if not texto_edital:
                    texto_edital = vaga.get("descricao_resumida", "Descrição indisponível.")
                prompt += f"\n--- VAGA ID {j}: {vaga['orgao']} - {vaga['cargo']} ---\n{texto_edital[:80000]}\n"

            prompt += """
            Para cada vaga, dê uma nota de 0 a 100 representando a compatibilidade real
            entre as experiências do currículo e os requisitos exigidos.

            Retorne no formato JSON:
            [
                {
                    "id": 0,
                    "porcentagem": 85,
                    "justificativa": "breve explicação...",
                    "habilidades_encontradas": ["habilidade 1"],
                    "habilidades_faltantes": ["habilidade 2"]
                }
            ]
            """

            try:
                res_json = ai_engine.chamar_gemini_com_retry(
                    client, prompt, MODELOS_CV,
                    on_fallback=lambda old, new: st.toast(f"⚠️ Alternando de {old} para {new}..."),
                    system_instruction=system_cv,
                )

                for res in res_json:
                    id_vaga = res.get("id")
                    if not isinstance(id_vaga, int) or id_vaga < 0 or id_vaga >= len(lote):
                        continue

                    vaga_analisada = lote[id_vaga].copy()
                    vaga_analisada["porcentagem"] = res.get("porcentagem", 0)
                    vaga_analisada["justificativa"] = res.get("justificativa", "Sem justificativa.")
                    vaga_analisada["habilidades_encontradas"] = res.get("habilidades_encontradas", [])
                    vaga_analisada["habilidades_faltantes"] = res.get("habilidades_faltantes", [])

                    db.salvar_analise_cv(
                        conn, cv_hash, vaga_analisada["link"],
                        vaga_analisada["porcentagem"],
                        vaga_analisada["justificativa"],
                        vaga_analisada["habilidades_encontradas"],
                        vaga_analisada["habilidades_faltantes"],
                    )
                    resultados.append(vaga_analisada)

                # Commit após o lote inteiro (fix: antes era dentro do loop)
                conn.commit()

            except RuntimeError as e:
                logger.error(f"Análise de CV falhou: {e}")
                st.toast("⚠️ Erro ao analisar com IA. Alguns editais podem ter sido ignorados.")

            barra.progress(min((i_batch + LOTE_CV) / len(vagas_para_analisar), 1.0))
            if i_batch + LOTE_CV < len(vagas_para_analisar):
                time.sleep(MODELOS_CV[0]["pausa"])

        barra.empty()
        texto_status.empty()
        return sorted(resultados, key=lambda x: x.get("porcentagem", 0), reverse=True)

    finally:
        conn.close()


# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
def main():
    st.set_page_config(page_title="Caçador de Concursos IA (V2 MCP)", layout="wide")

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        st.info("💡 V2: Integrada via protocolo MCP.")

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

    # --- HEADER ---
    st.title("🎯 Caçador de Concursos com IA (V2)")
    st.markdown("Buscando concursos usando **Model Context Protocol (MCP)**.")

    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ Configure a chave GEMINI_API_KEY no arquivo `.streamlit/secrets.toml`.")
        st.stop()

    # --- PROFISSÕES ---
    st.header("1. O que você está buscando?")

    profissoes_salvas = []
    try:
        conn = db.get_connection()
        try:
            db.migrate(conn)
            profissoes_salvas = db.buscar_profissoes_salvas(conn)
        finally:
            conn.close()
    except Exception:
        pass

    if profissoes_salvas:
        profissoes_selecionadas = st.multiselect(
            "Selecione áreas que já estão no banco:", options=profissoes_salvas
        )
    else:
        profissoes_selecionadas = []

    novas_profissoes = st.text_input(
        "Adicione novas áreas (separe por vírgula):",
        placeholder="Ex: UX Researcher, Product Designer...",
    )

    todas_profissoes = profissoes_selecionadas.copy()
    if novas_profissoes:
        todas_profissoes.extend([p.strip() for p in novas_profissoes.split(",") if p.strip()])

    # Deduplica mantendo a ordem
    profissoes_unicas = {}
    for p in todas_profissoes:
        chave = p.lower()
        if chave not in profissoes_unicas:
            profissoes_unicas[chave] = p
    todas_profissoes = list(profissoes_unicas.values())
    profissao_final = ", ".join(todas_profissoes)

    if todas_profissoes:
        cols = st.columns(len(todas_profissoes))
        for col, p in zip(cols, todas_profissoes):
            col.markdown(f"🏷️ **{p}**")

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

    pode_buscar = profissao_final and (
        modo_busca == "Por Região"
        or (modo_busca == "Por Cargo" and cargo_busca)
        or (modo_busca == "Por Cidade" and cidade_busca and uf_busca)
    )

    if st.button("🔍 Buscar Vagas Abertas", type="primary", disabled=not pode_buscar):
        modo = "regiao"
        if modo_busca == "Por Cargo":
            modo = "cargo"
        elif modo_busca == "Por Cidade":
            modo = "cidade"

        vagas_encontradas = buscar_concursos_abertos(
            profissao_final, modo,
            regiao=regiao_api, cargo=cargo_busca,
            uf=uf_busca, cidade=cidade_busca,
        )

        if vagas_encontradas:
            st.success(f"📋 {len(vagas_encontradas)} editais abertos. Filtrando com IA...")
            vagas_filtradas = filtrar_vagas_por_profissao(profissao_final, vagas_encontradas)
            st.session_state.vagas_compativeis = vagas_filtradas
            st.success(f"✅ Filtro concluído! **{len(vagas_filtradas)} vagas** da sua área.")
        else:
            st.warning("Nenhuma vaga encontrada. Tente outros filtros.")

    # --- RESULTADOS ---
    if st.session_state.vagas_compativeis:
        st.write("### Vagas Encontradas:")

        for v in st.session_state.vagas_compativeis:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    st.markdown(f"**{v['orgao']}**")
                    st.caption(f"📋 {v['cargo'][:150]}...")
                with col2:
                    local = v.get("uf") or v.get("regiao")
                    if local:
                        st.metric("📍 Local", local.upper())
                with col3:
                    if v.get("salario"):
                        st.metric("💰 Salário", v["salario"])

                # Info extra
                extras = []
                dias = v.get("dias_restantes", 0)
                if dias and isinstance(dias, int):
                    if dias > 0:
                        extras.append(f"⏰ {dias} dias restantes")
                    elif dias == 0:
                        extras.append("⚠️ Último dia!")
                datas_texto = v.get("datas_texto", "")
                if datas_texto:
                    extras.append(f"📌 {datas_texto}")
                if extras:
                    st.caption(" | ".join(extras))

        # --- CURRÍCULO ---
        st.header("2. Analisar Currículo")

        conn = db.get_connection()
        try:
            db.migrate(conn)
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
                    cv_hash = hashlib.md5(texto_cv.encode("utf-8")).hexdigest()
                    data_atual = time.strftime("%d/%m/%Y às %H:%M")

                    conn = db.get_connection()
                    try:
                        db.migrate(conn)
                        db.salvar_curriculo(conn, cv_hash, arquivo_pdf.name, data_atual, texto_cv)
                    finally:
                        conn.close()
        else:
            texto_cv = dict_cvs[escolha_cv]["texto"]

        if texto_cv and st.button("📊 Calcular Compatibilidade"):
            with st.spinner("Lendo currículo e cruzando dados..."):
                ranking = calcular_compatibilidade_curriculo(texto_cv, st.session_state.vagas_compativeis)

                st.write("### 🏆 Ranking de Compatibilidade")
                for item in ranking:
                    porcentagem = item.get("porcentagem", 0)

                    with st.container(border=True):
                        col1, col2 = st.columns([4, 1])

                        with col1:
                            st.markdown(f"#### {item['orgao']}")

                            # Badges de local e salário
                            badges = []
                            local = item.get("uf") or item.get("regiao")
                            if local:
                                badges.append(f"📍 {local.upper()}")
                            if item.get("salario"):
                                badges.append(f"💰 {item['salario']}")
                            if badges:
                                st.caption(" | ".join(badges))

                            st.caption(f"**Cargo(s):** {item['cargo'][:200]}")
                            st.markdown(f"**Por que?** {item.get('justificativa', '')}")

                        with col2:
                            cor = "normal" if porcentagem >= 75 else "off" if porcentagem >= 50 else "inverse"
                            st.metric("Match", f"{porcentagem}%", delta_color=cor)

                        # Tags de habilidades
                        hab_enc = item.get("habilidades_encontradas", [])
                        hab_falt = item.get("habilidades_faltantes", [])
                        if hab_enc or hab_falt:
                            tags_cols = st.columns(len(hab_enc) + len(hab_falt)) if (len(hab_enc) + len(hab_falt)) <= 6 else [st.container()]
                            tag_texts = []
                            for h in hab_enc:
                                tag_texts.append(f"✅ {h}")
                            for h in hab_falt:
                                tag_texts.append(f"❌ Falta: {h}")
                            st.caption(" | ".join(tag_texts))

                        st.link_button("📄 Acessar Edital Oficial", item["link"])


if __name__ == "__main__":
    main()