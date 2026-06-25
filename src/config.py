"""
Configurações centralizadas do Caçador de Concursos IA.
Constantes, caminhos, modelos de IA e gerenciamento de API key.
"""
import os
import json
import logging
from logging.handlers import RotatingFileHandler

try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None

# ==========================================
# CAMINHOS
# ==========================================
DB_PATH = "data/concursos_v2.db"
LOG_DIR = "logs"

# Raiz do projeto (pasta acima de src/) — para caminhos absolutos independentes do cwd
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIARIA_PATH = os.path.join(PROJECT_ROOT, "config_diaria.json")

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
# TAMANHOS DE LOTE E LIMITES
# ==========================================
LOTE_PENTE_FINO = 100
LOTE_FILTRO = 50
LOTE_CV = 5

# Limite de caracteres por edital enviado ao LLM (~15K tokens, seguro para a maioria dos modelos)
MAX_CHARS_POR_EDITAL = 60000

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
# CONFIG DA BUSCA DIÁRIA
# ==========================================
CONFIG_DIARIA_DEFAULTS = {
    "ativa": False,
    "profissoes": [
        "Service Designer (Júnior)", "Product Designer (Júnior)",
        "UX/UI Designer (Júnior)", "UI/UX Designer (Júnior)", "UX Researcher (Júnior)",
    ],
    "regioes": [""],
    "analisar_curriculo": True,
    "horario": 9,
}

logger = logging.getLogger(__name__)


def carregar_config_diaria() -> dict:
    """Lê config_diaria.json mesclado com os defaults. Tolerante a arquivo ausente/inválido."""
    config = dict(CONFIG_DIARIA_DEFAULTS)
    try:
        with open(CONFIG_DIARIA_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"config_diaria.json inválido, usando defaults: {e}")
    return config


def salvar_config_diaria(config: dict) -> None:
    """Persiste a config da busca diária em config_diaria.json (preserva chaves existentes)."""
    atual = carregar_config_diaria()
    atual.update(config)
    with open(CONFIG_DIARIA_PATH, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=4)


# ==========================================
# API KEY
# ==========================================
def get_api_key() -> str:
    """
    Obtém a chave da API Gemini de forma segura.
    Prioridade: variável de ambiente > st.secrets > .streamlit/secrets.toml (leitura direta).
    Retorna string vazia se não encontrada (a validação fica na UI).
    """
    # 1. Variável de ambiente (mais seguro, funciona em qualquer contexto)
    env_key = os.getenv("GEMINI_API_KEY", "")
    if env_key:
        return env_key

    # 2. Streamlit secrets (quando rodando via streamlit run)
    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    # 3. Leitura direta do arquivo secrets.toml (para execução headless/CLI)
    secrets_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".streamlit", "secrets.toml",
    )
    try:
        if tomllib is not None:
            with open(secrets_path, "rb") as f:
                secrets = tomllib.load(f)
            return secrets.get("GEMINI_API_KEY", "")
        else:
            # Fallback manual para Python 3.10
            with open(secrets_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY"):
                        _, _, valor = line.partition("=")
                        return valor.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass

    return ""
