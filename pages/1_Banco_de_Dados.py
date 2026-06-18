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

st.set_page_config(page_title="Banco de Dados - Caçador IA", page_icon="📚", layout="wide")

st.title("📚 Banco de Dados de Concursos")
st.markdown("Gerencie, filtre e acompanhe todas as vagas que o robô já encontrou e salvou.")

db_file = db.DB_PATH

if not os.path.exists(db_file):
    st.info("O banco de dados ainda não foi criado. Faça sua primeira busca!")
    st.stop()

conn = db.get_connection()
try:
    db.migrate(conn)

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

    st.write(f"Total de registros armazenados: **{len(vagas_bd)}**")

    # --- FILTROS ---
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
        # Colunas: inscrito(0), orgao(1), cargo(2), descricao(3), status(4), link(5),
        #          data_enc(6), salario(7), formacao(8), regiao(9), uf(10),
        #          dias_restantes(11), datas_texto(12)
        inscrito = bool(v[0])
        if mostrar_inscritos and not inscrito:
            continue

        orgao = v[1] or ""
        cargo = v[2] or ""
        descricao = v[3] or ""
        status = v[4] or ""

        # Filtra encerrados (padrão: escondidos)
        if status == "encerrado" and not mostrar_encerrados:
            continue

        if termo_busca and termo_busca.lower() not in orgao.lower() \
                and termo_busca.lower() not in cargo.lower() \
                and termo_busca.lower() not in descricao.lower():
            continue

        link_vaga = v[5] or ""
        data_enc = v[6] if len(v) > 6 else "Não informada"
        salario = v[7] if len(v) > 7 else ""
        formacao = v[8] if len(v) > 8 else ""
        regiao = v[9] if len(v) > 9 else ""
        uf = v[10] if len(v) > 10 else ""
        dias_rest = v[11] if len(v) > 11 else 0
        datas_texto = v[12] if len(v) > 12 else ""
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

    df_editado = st.data_editor(
        dados_formatados,
        column_config={
            "Inscrito": st.column_config.CheckboxColumn("Inscrito?", default=False),
            "Link": st.column_config.LinkColumn("Edital"),
            "_link_db": None,
        },
        disabled=["Órgão", "Cargo/Status", "Áreas Compatíveis", "Resumo/Descrição",
                   "Link", "Dias Rest.", "Info"],
        use_container_width=True,
        hide_index=True,
    )

    # Salva mudanças de inscrição
    for i in range(len(dados_formatados)):
        if dados_formatados[i]["Inscrito"] != df_editado[i]["Inscrito"]:
            novo_status = 1 if df_editado[i]["Inscrito"] else 0
            db.atualizar_inscricao(conn, dados_formatados[i]["_link_db"], novo_status)
            st.toast("Status de inscrição salvo!")

    # --- EXPORTAÇÃO ---
    st.markdown("---")
    st.subheader("📥 Exportação e Análise Avançada")
    st.markdown("Baixe seus dados para o Excel ou exporte para uso manual no Gemini.")

    col1, col2 = st.columns(2)

    with col1:
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
            use_container_width=True,
        )

    with col2:
        vagas_abertas = [
            {
                "orgao": v[1], "cargo": v[2], "encerramento": v[6] if len(v) > 6 else "",
                "salario": v[7] if len(v) > 7 else "",
                "local": (v[10] or v[9]) if len(v) > 10 else "",
                "descricao": v[3], "link": v[5],
            }
            for v in vagas_bd if v[4] == "aberto"
        ]
        st.download_button(
            label="🤖 Baixar Vagas Abertas (JSON para IA)",
            data=json.dumps(vagas_abertas, ensure_ascii=False, indent=2),
            file_name="vagas_abertas_gemini.json",
            mime="application/json",
            use_container_width=True,
        )

    with st.expander("Passo a passo de como analisar na web"):
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
