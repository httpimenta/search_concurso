"""
📚 Banco de Dados de Concursos
Página de gestão, filtro e acompanhamento das vagas encontradas.
"""
import streamlit as st
import json
import csv
import io
import os

from src import db
from src.styles import inject_css, hero, stat_card, section_header, status_badge

st.set_page_config(page_title="Banco de Dados - Caçador IA", page_icon="📚", layout="wide")
inject_css()

hero(
    "📚 Banco de Dados de Concursos",
    "Gerencie, filtre e acompanhe todas as vagas que o robô já encontrou e salvou.",
)

db_file = db.DB_PATH

if not os.path.exists(db_file):
    st.info("O banco de dados ainda não foi criado. Faça sua primeira busca!")
    st.stop()

conn = db.get_connection()
try:
    vagas_bd = db.buscar_todas_vagas(conn)

    # Busca as tags/profissões compatíveis
    tags_por_link: dict[str, list[str]] = {}
    try:
        c = conn.cursor()
        c.execute("SELECT link, profissao FROM analises_filtro WHERE compativel = 1")
        for link, prof in c.fetchall():
            if link not in tags_por_link:
                tags_por_link[link] = []
            tags_por_link[link].append(prof)
    except Exception:
        pass

    if not vagas_bd:
        st.info("O banco de dados está criado, mas ainda está vazio.")
        st.stop()

    # --- MINI DASHBOARD ---
    total = len(vagas_bd)
    abertas = sum(1 for v in vagas_bd if v["status"] == "aberto")
    encerradas = sum(1 for v in vagas_bd if v["status"] == "encerrado")
    inscritas = sum(1 for v in vagas_bd if v["inscrito"])

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        stat_card("📊", total, "Total de vagas")
    with col_s2:
        stat_card("✅", abertas, "Abertas")
    with col_s3:
        stat_card("📦", encerradas, "Encerradas")
    with col_s4:
        stat_card("🎯", inscritas, "Inscritas")

    st.markdown("")

    # --- FILTROS ---
    section_header("🔎", "Filtros")
    col_filtros1, col_filtros2, col_filtros3 = st.columns([1, 1, 2])
    with col_filtros1:
        mostrar_inscritos = st.toggle("🎯 Apenas inscritos")
    with col_filtros2:
        mostrar_encerrados = st.toggle("📦 Mostrar encerrados")
    with col_filtros3:
        termo_busca = st.text_input(
            "🔍 Buscar vaga específica (Órgão, Cargo ou Palavra-chave)", ""
        )

    # --- TABELA ---
    dados_formatados = []
    for v in vagas_bd:
        inscrito = v["inscrito"]
        if mostrar_inscritos and not inscrito:
            continue

        orgao = v["orgao"]
        cargo = v["cargo"]
        descricao = v["descricao_resumida"]
        status = v["status"]

        # Filtra encerrados (padrão: escondidos)
        if status == "encerrado" and not mostrar_encerrados:
            continue

        if termo_busca and termo_busca.lower() not in orgao.lower() \
                and termo_busca.lower() not in cargo.lower() \
                and termo_busca.lower() not in descricao.lower():
            continue

        link_vaga = v["link"]
        data_enc = v["data_encerramento"]
        salario = v["salario"]
        formacao = v["formacao"]
        regiao = v["regiao"]
        uf = v["uf"]
        dias_rest = v["dias_restantes"]
        datas_texto = v["datas_texto"]
        local = uf.upper() if uf else regiao.upper()
        tags_vaga = ", ".join(tags_por_link.get(link_vaga, [])) or "-"

        dados_formatados.append({
            "Inscrito": inscrito,
            "Órgão": orgao,
            "Cargo/Status": cargo,
            "Local": local,
            "Salário": salario,
            "Áreas Compatíveis": tags_vaga,
            "Encerramento": data_enc,
            "Dias Rest.": dias_rest if isinstance(dias_rest, int) else 0,
            "Info": datas_texto or "",
            "Resumo/Descrição": descricao,
            "Link": link_vaga,
            "_link_db": link_vaga,
        })

    if not dados_formatados:
        st.info("Nenhuma vaga corresponde ao filtro atual.")
        st.stop()

    st.caption(f"Mostrando **{len(dados_formatados)}** vagas com os filtros atuais")

    df_editado = st.data_editor(
        dados_formatados,
        column_config={
            "Inscrito": st.column_config.CheckboxColumn("Inscrito?", default=False),
            "Link": st.column_config.LinkColumn("Edital"),
            "_link_db": None,
        },
        disabled=["Órgão", "Cargo/Status", "Local", "Salário", "Áreas Compatíveis",
                   "Encerramento", "Resumo/Descrição", "Link", "Dias Rest.", "Info"],
        width="stretch",
        hide_index=True,
    )

    # Salva mudanças de inscrição
    for i in range(len(dados_formatados)):
        if dados_formatados[i]["Inscrito"] != df_editado[i]["Inscrito"]:
            novo_status = 1 if df_editado[i]["Inscrito"] else 0
            db.atualizar_inscricao(conn, dados_formatados[i]["_link_db"], novo_status)
            st.toast("Status de inscrição salvo!")

    # --- EXPORTAÇÃO ---
    st.markdown("")
    section_header("📥", "Exportação e Análise Avançada")
    st.markdown("Baixe seus dados para o Excel ou exporte para uso manual no Gemini.")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("#### 📊 Exportar CSV")
            st.caption("Compatível com Excel, Google Sheets e outros.")
            csv_buffer = io.StringIO()
            fieldnames = ["Inscrito", "Órgão", "Cargo/Status", "Local", "Salário",
                           "Áreas Compatíveis", "Encerramento", "Resumo/Descrição", "Link"]
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            for row in dados_formatados:
                row_copy = {k: row[k] for k in fieldnames}
                row_copy["Inscrito"] = "Sim" if row_copy["Inscrito"] else "Não"
                writer.writerow(row_copy)

            st.download_button(
                label="📊 Baixar Tabela (CSV / Excel)",
                data=csv_buffer.getvalue().encode("utf-8-sig"),
                file_name="vagas_concursos.csv",
                mime="text/csv",
                width="stretch",
            )

    with col2:
        with st.container(border=True):
            st.markdown("#### 🤖 Exportar JSON")
            st.caption("Para uso com o Gemini, ChatGPT ou outros modelos de IA.")
            vagas_abertas = [
                {
                    "orgao": v["orgao"],
                    "cargo": v["cargo"],
                    "encerramento": v["data_encerramento"],
                    "salario": v["salario"],
                    "local": v["uf"] or v["regiao"],
                    "descricao": v["descricao_resumida"],
                    "link": v["link"],
                }
                for v in vagas_bd if v["status"] == "aberto"
            ]
            st.download_button(
                label="🤖 Baixar Vagas Abertas (JSON para IA)",
                data=json.dumps(vagas_abertas, ensure_ascii=False, indent=2),
                file_name="vagas_abertas_gemini.json",
                mime="application/json",
                width="stretch",
            )

    with st.expander("💡 Passo a passo de como analisar na web"):
        st.markdown("""
        **1.** Baixe o arquivo JSON no botão acima.
        **2.** Acesse [gemini.google.com](https://gemini.google.com).
        **3.** Faça o upload do arquivo JSON baixado **e também** do seu Currículo em PDF.
        **4.** Copie e cole o prompt abaixo no chat (substituindo sua profissão):
        """)
        st.code(
            'Você é um recrutador especialista e um sistema avançado de ATS. '
            'Em anexo estão as vagas de concursos abertas (JSON) e o meu currículo (PDF). '
            'Meu perfil principal é: [SUA PROFISSÃO AQUI].\n\n'
            'Siga estes passos e me dê o resultado final:\n'
            '1. Analise o arquivo JSON e filtre apenas as vagas compatíveis com meu perfil.\n'
            '2. Cruze os requisitos dessas vagas filtradas com as experiências do meu currículo.\n'
            '3. Crie um ranking apenas com as vagas compatíveis, exibindo para cada uma:\n'
            '- Órgão e Cargo Oficial\n'
            '- Porcentagem de Match (0 a 100%)\n'
            '- Breve justificativa baseada no currículo\n'
            '- Link do edital',
            language="text",
        )

finally:
    conn.close()
