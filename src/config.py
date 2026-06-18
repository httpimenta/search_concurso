"""
Configurações centralizadas do Caçador de Concursos IA.
Constantes, caminhos, modelos de IA e gerenciamento de API key.
"""
import os
import logging
from logging.handlers import RotatingFileHandler

# ==========================================
# CAMINHOS
# ==========================================
DB_PATH = "data/concursos_v2.db"
LOG_DIR = "logs"

# ==========================================
# HTTP
# ==========================================
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

MCP_BASE_URL = "https://www.pciconcursos.com.br/mcp"

# ==========================================
# MODELOS GEMINI (ordenados por prioridade)
# ==========================================
MODELOS_PENTE_FINO = [
    {"nome": "gemini-3.1-flash-lite", "pausa": 5},
    {"nome": "gemini-flash-latest", "pausa": 15},
    {"nome": "gemini-2.5-flash", "pausa": 15},
]

MODELOS_FILTRO = [
    {"nome": "gemini-flash-latest", "pausa": 15},
    {"nome": "gemini-3.1-flash-lite", "pausa": 5},
    {"nome": "gemini-2.5-flash", "pausa": 15},
]

MODELOS_CV = [
    {"nome": "gemini-flash-latest", "pausa": 15},
    {"nome": "gemini-2.5-flash", "pausa": 15},
    {"nome": "gemini-2.0-flash", "pausa": 15},
    {"nome": "gemini-3.1-flash-lite", "pausa": 5},
]

# ==========================================
# TAMANHOS DE LOTE
# ==========================================
LOTE_PENTE_FINO = 100
LOTE_FILTRO = 50
LOTE_CV = 5

# ==========================================
# LOGGING
# ==========================================
def setup_logging():
    """Configura o sistema de logs com rotação de arquivo."""
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    log_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "cacador_concursos_v2.log"),
        maxBytes=1 * 1024 * 1024,
        backupCount=3,
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[log_handler],
    )


def setup_page_logger(nome: str, arquivo_log: str) -> logging.Logger:
    """Cria um logger independente para páginas secundárias (Laboratório, etc.)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(nome)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(arquivo_log, maxBytes=1 * 1024 * 1024, backupCount=3)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.propagate = False
    return logger


# ==========================================
# API KEY
# ==========================================
def get_api_key() -> str:
    """
    Obtém a chave da API Gemini de forma segura.
    Prioridade: st.secrets > variável de ambiente > erro.
    Retorna string vazia se não encontrada (a validação fica na UI).
    """
    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    return os.getenv("GEMINI_API_KEY", "")
