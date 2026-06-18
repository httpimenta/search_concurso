"""
Cliente MCP para comunicação com a API do PCI Concursos.
Usa a estrutura real da API (confirmada via chamadas diretas).
"""
from __future__ import annotations
import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from src.config import MCP_BASE_URL, USER_AGENT
from src.models import Vaga

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
}


def _post_mcp(method: str, tool_name: str, arguments: dict) -> dict:
    """Envia um comando JSON-RPC ao servidor MCP."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {"name": tool_name, "arguments": arguments},
    }
    logger.info(f"MCP POST → {tool_name} | args: {arguments}")
    response = requests.post(MCP_BASE_URL, headers=HEADERS, json=payload, timeout=15)
    return response.json()


def _extrair_data(resposta: dict) -> list[dict]:
    """
    Extrai a lista de vagas da resposta MCP.
    A API retorna consistentemente: { "result": { "content": [{ "text": "{ meta, data }" }] } }
    """
    try:
        # Fallback: lista direta (deve ser verificado primeiro)
        if isinstance(resposta, list):
            return resposta

        # Caminho principal: JSON-RPC → result → content → text → JSON real
        resultado = resposta.get("result", {})
        if isinstance(resultado, dict) and "content" in resultado:
            conteudo = resultado["content"]
            if isinstance(conteudo, list) and conteudo:
                import json
                texto = conteudo[0].get("text", "{}")
                dados = json.loads(texto)
                if isinstance(dados, dict) and "data" in dados:
                    return dados["data"]
                if isinstance(dados, list):
                    return dados

        # Fallback: resposta direta com campo "data"
        if isinstance(resposta, dict) and "data" in resposta:
            return resposta["data"]

    except Exception as e:
        logger.error(f"Erro ao extrair dados da resposta MCP: {e}")

    return []


# ==========================================
# ENDPOINTS PÚBLICOS
# ==========================================
def fetch_concursos(regiao: str = "", professores: bool = False) -> list[dict]:
    """
    Lista concursos com filtros opcionais.
    Retorna a lista de dicts crus da API.
    """
    args: dict = {}
    if regiao:
        args["regiao"] = regiao
    if professores:
        args["professores"] = True

    resposta = _post_mcp("tools/call", "listar_concursos", args)
    return _extrair_data(resposta)


def pesquisar_concursos(termo: str, uf: str = "") -> list[dict]:
    """Busca concursos por termo livre."""
    args: dict = {"termo": termo}
    if uf:
        args["uf"] = uf

    resposta = _post_mcp("tools/call", "pesquisar_concursos", args)
    return _extrair_data(resposta)


def buscar_por_cargo(cargo: str, uf: str = "") -> list[dict]:
    """Busca concursos por cargo específico."""
    args: dict = {"cargo": cargo}
    if uf:
        args["uf"] = uf

    resposta = _post_mcp("tools/call", "buscar_por_cargo", args)
    return _extrair_data(resposta)


def buscar_por_cidade(uf: str, cidade: str) -> list[dict]:
    """Busca concursos por cidade."""
    args = {"uf": uf, "cidade": cidade}
    resposta = _post_mcp("tools/call", "buscar_por_cidade", args)
    return _extrair_data(resposta)


# ==========================================
# PARSING
# ==========================================
def parse_vagas(data: list[dict]) -> list[Vaga]:
    """Converte a lista de dicts da API em lista de objetos Vaga tipados."""
    vagas = []
    for d in data:
        try:
            vagas.append(Vaga.from_api_dict(d))
        except Exception as e:
            logger.warning(f"Erro ao parsear vaga: {e} | Dados: {str(d)[:200]}")
    return vagas


# ==========================================
# EXTRAÇÃO DE CONTEÚDO HTML
# ==========================================
def extrair_texto_pagina(url: str) -> str | None:
    """Baixa uma página de notícia e extrai o conteúdo textual."""
    try:
        res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        conteudo = soup.find("div", class_="j-noticia") or soup.find("article")
        if conteudo:
            return conteudo.text.strip()
    except Exception as e:
        logger.error(f"Erro ao extrair texto de {url}: {e}")
    return None


def extrair_texto_paginas_paralelo(urls: list[str], max_workers: int = 5) -> dict[str, str | None]:
    """
    Extrai o texto de múltiplas páginas em paralelo usando ThreadPoolExecutor.
    Retorna: {url: texto_extraido_ou_None}
    """
    resultados: dict[str, str | None] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(extrair_texto_pagina, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                resultados[url] = future.result()
            except Exception as e:
                logger.error(f"Erro paralelo em {url}: {e}")
                resultados[url] = None

    return resultados
