"""
Utilitários de extração de texto de PDFs.
Usado para currículos e editais de concurso.
"""
from __future__ import annotations
import logging
import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import pymupdf4llm
from src.config import USER_AGENT
from src import db

logger = logging.getLogger(__name__)


def extrair_texto_pdf(arquivo_pdf) -> str:
    """
    Converte um PDF de currículo para Markdown preservando tabelas e formatação.

    Args:
        arquivo_pdf: Objeto com método .getvalue() (ex: UploadedFile do Streamlit)

    Returns:
        Texto em formato Markdown
    """
    doc = fitz.open(stream=arquivo_pdf.getvalue(), filetype="pdf")
    return pymupdf4llm.to_markdown(doc)


def extrair_texto_edital_pdf(url_vaga: str, conn) -> str | None:
    """
    Acessa a página da vaga, busca o link do edital oficial em PDF e extrai o texto.
    Usa cache do banco de dados para evitar re-downloads.

    Args:
        url_vaga: URL da notícia da vaga
        conn: Conexão SQLite ativa

    Returns:
        Texto do edital em Markdown ou None se não encontrado
    """
    # 1. Verifica o cache
    texto_cache = db.buscar_texto_edital(conn, url_vaga)
    if texto_cache:
        return texto_cache

    # 2. Busca na página
    try:
        res = requests.get(url_vaga, headers={"User-Agent": USER_AGENT}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        pdf_link = None
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            texto = a.text.lower()
            if ("edital" in texto or ".pdf" in href) and (
                "arquivo.pciconcursos" in href or ".pdf" in href
            ):
                pdf_link = a["href"]
                break

        if pdf_link:
            if pdf_link.startswith("//"):
                pdf_link = "https:" + pdf_link
            elif pdf_link.startswith("/"):
                pdf_link = "https://www.pciconcursos.com.br" + pdf_link

            pdf_res = requests.get(
                pdf_link, headers={"User-Agent": USER_AGENT}, timeout=15
            )
            if pdf_res.status_code == 200:
                doc = fitz.open(stream=pdf_res.content, filetype="pdf")
                texto_edital = pymupdf4llm.to_markdown(doc)

                # 3. Salva no cache
                db.salvar_texto_edital(conn, url_vaga, texto_edital)
                return texto_edital

    except Exception as e:
        logger.error(f"Erro ao extrair PDF do edital de {url_vaga}: {e}")

    return None
