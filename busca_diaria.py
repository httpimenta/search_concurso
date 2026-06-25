#!/usr/bin/env python3
"""
🎯 Caçador de Concursos — Busca Diária Automatizada
=====================================================
Script headless (sem UI) que roda diariamente via launchd.

Pipeline:
  1. Carrega configuração de config_diaria.json
  2. Puxa TODOS os concursos do MCP (sem filtrar por profissão na API)
  3. Salva no banco SQLite
  4. Filtra com IA (Pente Fino + Filtro Detalhado)
  5. Opcionalmente analisa currículo salvo
  6. Gera relatório HTML rico em resultados/
"""
import os
import sys
import time
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Garante que o diretório do projeto é o working directory
SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)
sys.path.insert(0, str(SCRIPT_DIR))

from src.config import get_api_key, carregar_config_diaria
from src import db, mcp_client
from src.pipeline import (
    PipelineCallbacks, salvar_vagas_no_banco,
    executar_pente_fino_e_extracao, filtrar_vagas_por_profissao,
    analisar_curriculo,
)
from src.report import gerar_relatorio_html

# ──────────────────────────────────────────────
# Logging (console + arquivo)
# ──────────────────────────────────────────────
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

RESULTADOS_DIR = SCRIPT_DIR / "resultados"
RESULTADOS_DIR.mkdir(exist_ok=True)

DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def setup_cli_logging() -> logging.Logger:
    """Configura logging para console + arquivo rotativo."""
    logger = logging.getLogger("busca_diaria")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Arquivo rotativo
    fh = RotatingFileHandler(
        LOG_DIR / "busca_diaria.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


logger = setup_cli_logging()


def _criar_callbacks_cli() -> PipelineCallbacks:
    """Cria callbacks do pipeline para modo headless (CLI)."""
    return PipelineCallbacks(
        on_info=lambda msg: logger.info(msg),
        on_warning=lambda msg: logger.warning(msg),
        on_error=lambda msg: logger.error(msg),
        on_status=lambda msg: logger.info(msg.replace("**", "")),
        on_toast=lambda msg: logger.info(msg),
    )


# ──────────────────────────────────────────────
# Carregar configuração
# ──────────────────────────────────────────────
def carregar_config() -> dict:
    """Carrega config_diaria.json (defaults centralizados em src.config)."""
    config = carregar_config_diaria()
    logger.info("Configuração da busca diária carregada")
    return config


# ──────────────────────────────────────────────
# Pipeline de busca (MCP)
# ──────────────────────────────────────────────
def buscar_todas_vagas_mcp(regioes: list[str]) -> list[dict]:
    """
    Puxa TODOS os concursos do MCP para cada região configurada.
    Não filtra por profissão na API — a IA filtra depois.
    """
    todas_vagas = []
    seen_ids = set()

    for regiao in regioes:
        regiao_label = regiao if regiao else "Nacional"
        logger.info(f"📡 Buscando concursos - região: {regiao_label}")

        try:
            vagas_brutas = mcp_client.fetch_concursos(regiao)
            if vagas_brutas:
                for vaga in vagas_brutas:
                    vaga_id = vaga.get("id", id(vaga))
                    if vaga_id not in seen_ids:
                        seen_ids.add(vaga_id)
                        todas_vagas.append(vaga)
                logger.info(f"  → {len(vagas_brutas)} vagas da região {regiao_label}")
            else:
                logger.warning(f"  → Nenhuma vaga retornada para {regiao_label}")
        except Exception as e:
            logger.error(f"  ✗ Erro na região {regiao_label}: {e}")

    logger.info(f"📊 Total de vagas brutas (únicas): {len(todas_vagas)}")
    return todas_vagas


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    inicio = time.time()
    timestamp = datetime.now().strftime("%d/%m/%Y às %H:%M")
    timestamp_file = datetime.now().strftime("%Y-%m-%d_%H%M")

    logger.info("=" * 60)
    logger.info("🎯 CAÇADOR DE CONCURSOS — Busca Diária Automatizada")
    logger.info(f"📅 {timestamp}")
    logger.info("=" * 60)

    # Carregar config
    config = carregar_config()

    # Respeita o toggle definido no app Streamlit
    if not config.get("ativa", True):
        logger.info("⏸️  Busca diária DESATIVADA no app (config_diaria.json: \"ativa\": false). Encerrando.")
        return

    profissoes = config["profissoes"]
    regioes = config["regioes"]
    analisar_cv = config.get("analisar_curriculo", True)

    logger.info(f"🔍 Profissões: {profissoes}")
    logger.info(f"📍 Regiões: {[r or 'Nacional' for r in regioes]}")

    # Verificar API key
    api_key = get_api_key()
    if not api_key:
        logger.error("❌ GEMINI_API_KEY não encontrada! Configure em .streamlit/secrets.toml ou variável de ambiente.")
        sys.exit(1)

    logger.info("🔑 API Key encontrada ✓")

    cb = _criar_callbacks_cli()

    # 1. Buscar TODAS as vagas do MCP
    logger.info("")
    logger.info("─" * 40)
    logger.info("ETAPA 1: Busca no MCP")
    logger.info("─" * 40)
    vagas_brutas = buscar_todas_vagas_mcp(regioes)
    total_brutas = len(vagas_brutas)

    if not vagas_brutas:
        logger.warning("⚠️ Nenhuma vaga retornada pelo MCP. Encerrando.")
        return

    # 2. Salvar no banco
    logger.info("")
    logger.info("─" * 40)
    logger.info("ETAPA 2: Salvando no banco de dados")
    logger.info("─" * 40)
    novas, _, _ = salvar_vagas_no_banco(vagas_brutas, cb)

    # 3. Pente Fino + Extração de texto
    logger.info("")
    logger.info("─" * 40)
    logger.info("ETAPA 3: Pente Fino + Extração de Texto")
    logger.info("─" * 40)
    executar_pente_fino_e_extracao(profissoes, api_key, cb)

    # 4. Filtro detalhado
    logger.info("")
    logger.info("─" * 40)
    logger.info("ETAPA 4: Filtro Detalhado com IA")
    logger.info("─" * 40)
    vagas_compativeis = filtrar_vagas_por_profissao(profissoes, api_key, cb)

    # 5. Análise de currículo (opcional)
    ranking_cv = None
    if analisar_cv and vagas_compativeis:
        logger.info("")
        logger.info("─" * 40)
        logger.info("ETAPA 5: Análise de Currículo")
        logger.info("─" * 40)

        # Busca o currículo mais recente
        conn = db.get_connection()
        try:
            cvs = db.buscar_curriculos(conn)
        finally:
            conn.close()

        if cvs:
            _, nome_arquivo, _, texto_cv = cvs[0]
            logger.info(f"📄 Usando currículo: {nome_arquivo}")
            ranking_cv = analisar_curriculo(texto_cv, vagas_compativeis, api_key, cb)
        else:
            logger.info("📄 Nenhum currículo salvo — pulando análise de CV")

    # 6. Contar vagas abertas no banco
    conn = db.get_connection()
    try:
        total_abertas = len(db.buscar_vagas_abertas(conn))
    finally:
        conn.close()

    # 7. Gerar relatório HTML
    logger.info("")
    logger.info("─" * 40)
    logger.info("ETAPA 6: Gerando Relatório HTML")
    logger.info("─" * 40)

    html = gerar_relatorio_html(
        vagas_compativeis=vagas_compativeis,
        ranking_cv=ranking_cv,
        profissoes=profissoes,
        timestamp=timestamp,
        total_brutas=total_brutas,
        total_abertas=total_abertas,
        novas=novas,
    )

    # Salvar com timestamp
    arquivo_datado = RESULTADOS_DIR / f"concursos_{timestamp_file}.html"
    arquivo_datado.write_text(html, encoding="utf-8")

    # Link simbólico para o mais recente
    arquivo_latest = RESULTADOS_DIR / "concursos_latest.html"
    if arquivo_latest.exists() or arquivo_latest.is_symlink():
        arquivo_latest.unlink()
    arquivo_latest.symlink_to(arquivo_datado.name)

    logger.info(f"📄 Relatório salvo: {arquivo_datado}")
    logger.info(f"📄 Link latest: {arquivo_latest}")

    # Resumo final
    duracao = time.time() - inicio
    logger.info("")
    logger.info("=" * 60)
    logger.info("🏁 BUSCA DIÁRIA CONCLUÍDA")
    logger.info(f"   ⏱️  Duração: {duracao:.1f}s")
    logger.info(f"   📊 Vagas brutas: {total_brutas}")
    logger.info(f"   💾 Novas: {novas}")
    logger.info(f"   🎯 Compatíveis: {len(vagas_compativeis)}")
    if ranking_cv:
        logger.info(f"   📄 Com análise CV: {len(ranking_cv)}")
    logger.info(f"   📁 Relatório: {arquivo_datado.name}")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⚠️ Execução interrompida pelo usuário")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Erro fatal: {e}")
        sys.exit(1)
