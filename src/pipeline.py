"""
Pipeline central de busca, filtragem e análise de concursos.
Centraliza toda a lógica de negócios compartilhada entre app_v2.py (UI) e busca_diaria.py (CLI).
Usa callbacks para reportar progresso de forma agnóstica ao frontend.
"""
from __future__ import annotations
import json
import time
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Callable

from src.config import (
    MODELOS_PENTE_FINO, MODELOS_FILTRO, MODELOS_CV,
    LOTE_PENTE_FINO, LOTE_FILTRO, LOTE_CV,
    MAX_CHARS_POR_EDITAL,
)
from src import db, mcp_client, ai_engine, pdf_utils
from src.prompts import PROMPT_PENTE_FINO, PROMPT_FILTRO, PROMPT_CV

logger = logging.getLogger(__name__)


# ==========================================
# CALLBACKS
# ==========================================
@dataclass
class PipelineCallbacks:
    """Callbacks para reportar progresso do pipeline de forma agnóstica ao frontend."""
    on_info: Callable[[str], None] = field(default_factory=lambda: lambda msg: None)
    on_warning: Callable[[str], None] = field(default_factory=lambda: lambda msg: None)
    on_error: Callable[[str], None] = field(default_factory=lambda: lambda msg: None)
    on_progress: Callable[[float], None] = field(default_factory=lambda: lambda pct: None)
    on_status: Callable[[str], None] = field(default_factory=lambda: lambda msg: None)
    on_fallback: Callable[[str, str], None] = field(default_factory=lambda: lambda old, new: None)
    on_toast: Callable[[str], None] = field(default_factory=lambda: lambda msg: None)
    on_done: Callable[[], None] = field(default_factory=lambda: lambda: None)


_EMPTY_CB = PipelineCallbacks()


# ==========================================
# ETAPA 1: SALVAR VAGAS NO BANCO
# ==========================================
def salvar_vagas_no_banco(vagas_brutas: list[dict],
                          cb: PipelineCallbacks = _EMPTY_CB) -> tuple[int, list[str], list[str]]:
    """
    Parseia vagas brutas da API, salva no banco e retorna (novas, links_ativos, links_encerrados).
    """
    conn = db.get_connection()
    try:
        vagas = mcp_client.parse_vagas(vagas_brutas)
        links_salvos = db.buscar_links_salvos(conn)
        links_ativos: list[str] = []
        links_encerrados: list[str] = []
        novas = 0

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
                novas += 1

        conn.commit()

        # Atualiza status aberto/encerrado
        db.atualizar_status_vagas(conn, links_ativos, links_encerrados)
        conn.commit()

        if novas > 0:
            cb.on_info(f"📥 {novas} editais novos encontrados!")

        logger.info(f"💾 {novas} vagas novas salvas no banco")
        return novas, links_ativos, links_encerrados

    finally:
        conn.close()


# ==========================================
# ETAPA 2: PENTE FINO + EXTRAÇÃO DE TEXTO
# ==========================================
def executar_pente_fino_e_extracao(profissoes: list[str], api_key: str,
                                    cb: PipelineCallbacks = _EMPTY_CB) -> None:
    """
    Avalia quais vagas são relevantes usando IA (Pente Fino)
    e extrai o texto completo das páginas das vagas aprovadas.
    """
    conn = db.get_connection()
    try:
        vagas_sem_texto = db.buscar_vagas_sem_texto(conn)
        if not vagas_sem_texto:
            logger.info("✅ Todas as vagas já possuem texto extraído")
            return

        logger.info(f"🔎 Pente Fino: {len(vagas_sem_texto)} vagas para avaliar")

        cache_pente = db.buscar_cache_filtro(conn, profissoes)
        vagas_para_extrair: list[dict] = []
        vagas_para_pente_fino: list[dict] = []

        for vaga in vagas_sem_texto:
            link = vaga["link"]
            link_cache = cache_pente.get(link, {})

            # Já rejeitada para todas as profissões → pula
            if all(p in link_cache and not link_cache[p] for p in profissoes):
                continue

            # Já aprovada para alguma profissão → extrai direto
            if any(link_cache.get(p) is True for p in profissoes):
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
                                vagas_para_extrair, profissoes, api_key, cb)

        # Extração paralela de texto das páginas
        if vagas_para_extrair:
            _executar_extracao_texto(conn, vagas_para_extrair, cb)

    finally:
        conn.close()


def _executar_pente_fino(conn, vagas_pente: list, vagas_sem_texto: list,
                          vagas_para_extrair: list, profissoes: list,
                          api_key: str, cb: PipelineCallbacks) -> None:
    """Usa a IA para filtrar rapidamente cargos irrelevantes."""
    client = ai_engine.get_client(api_key)
    total = len(vagas_pente)
    analises_batch: list[tuple[str, str, int]] = []

    logger.info(f"  🤖 Analisando {total} cargos com IA...")

    for i_batch in range(0, total, LOTE_PENTE_FINO):
        lote = vagas_pente[i_batch:i_batch + LOTE_PENTE_FINO]
        lote_num = (i_batch // LOTE_PENTE_FINO) + 1
        total_lotes = (total + LOTE_PENTE_FINO - 1) // LOTE_PENTE_FINO

        cb.on_status(
            f"**🔎 Pente Fino:** Analisando {total} cargos resumidos... "
            f"(lote {lote_num}/{total_lotes})"
        )
        logger.info(f"  📦 Lote {lote_num}/{total_lotes}...")

        prompt = PROMPT_PENTE_FINO.format(
            profissoes=profissoes,
            cargos=json.dumps(
                [{"id": v["id"], "cargo": v["cargo"], "orgao": v["orgao"]} for v in lote],
                ensure_ascii=False,
            ),
        )

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
            logger.error(f"  ✗ Pente Fino falhou: {e}")

        cb.on_progress(min((i_batch + LOTE_PENTE_FINO) / total, 1.0))

        if i_batch + LOTE_PENTE_FINO < total:
            time.sleep(MODELOS_PENTE_FINO[0]["pausa"])

    # Commit em lote
    if analises_batch:
        db.salvar_analises_filtro_batch(conn, analises_batch)
        conn.commit()

    cb.on_done()


def _executar_extracao_texto(conn, vagas: list, cb: PipelineCallbacks) -> None:
    """Extrai o texto completo das páginas das vagas relevantes (em paralelo)."""
    # Remove duplicatas
    vagas_unicas = {v["link"]: v for v in vagas}
    urls = list(vagas_unicas.keys())
    total = len(urls)

    cb.on_status(f"**⏳ Extraindo texto de {total} editais relevantes...**")
    logger.info(f"  ⏳ Extraindo texto de {total} editais...")

    resultados = mcp_client.extrair_texto_paginas_paralelo(urls, max_workers=5)

    for i, (url, texto) in enumerate(resultados.items()):
        db.marcar_texto_extraido(conn, url, texto)
        cb.on_progress((i + 1) / total)

    conn.commit()
    cb.on_done()
    logger.info("  ✅ Textos extraídos com sucesso")


# ==========================================
# ETAPA 3: FILTRO DETALHADO POR PROFISSÃO
# ==========================================
def filtrar_vagas_por_profissao(profissoes: list[str], api_key: str,
                                cb: PipelineCallbacks = _EMPTY_CB) -> list[dict]:
    """
    Filtra as vagas abertas usando IA, retornando apenas as compatíveis.
    Consulta o banco internamente — não precisa receber a lista de vagas.
    """
    conn = db.get_connection()
    try:
        vagas = db.buscar_vagas_abertas(conn)

        if not vagas:
            logger.info("📋 Nenhuma vaga aberta no banco")
            return []

        logger.info(f"🤖 Filtrando {len(vagas)} vagas abertas com IA...")

        cache = db.buscar_cache_filtro(conn, profissoes)
        vagas_compativeis: list[dict] = []
        vagas_para_analisar: list[dict] = []

        for vaga in vagas:
            link = vaga["link"]
            link_cache = cache.get(link, {})

            if any(link_cache.get(p) is True for p in profissoes):
                vagas_compativeis.append(vaga)
            elif all(p in link_cache and not link_cache[p] for p in profissoes):
                pass  # Já rejeitada
            else:
                vagas_para_analisar.append(vaga)

        logger.info(f"  ⚡ {len(vagas_compativeis)} do cache, {len(vagas_para_analisar)} para analisar")

        if not vagas_para_analisar:
            cb.on_toast("⚡ Histórico carregado do banco de dados (0 novas vagas para processar)!")
            return vagas_compativeis

        cb.on_info(f"🤖 Analisando {len(vagas_para_analisar)} vagas inéditas com IA...")

        client = ai_engine.get_client(api_key)
        total_lotes = (len(vagas_para_analisar) + LOTE_FILTRO - 1) // LOTE_FILTRO

        for i in range(0, len(vagas_para_analisar), LOTE_FILTRO):
            lote_num = (i // LOTE_FILTRO) + 1
            lote = vagas_para_analisar[i:i + LOTE_FILTRO]

            cb.on_status(f"**🤖 IA analisando editais: lote {lote_num}/{total_lotes}**")
            logger.info(f"  📦 Filtro detalhado: lote {lote_num}/{total_lotes}")

            vagas_simplificadas = [
                {"id": i + j, "cargo": v["cargo"], "descricao": v["descricao_resumida"]}
                for j, v in enumerate(lote)
            ]

            prompt = PROMPT_FILTRO.format(
                profissoes=profissoes,
                vagas=json.dumps(vagas_simplificadas, ensure_ascii=False),
            )

            try:
                resultados = ai_engine.chamar_gemini_com_retry(
                    client, prompt, MODELOS_FILTRO,
                    on_fallback=cb.on_fallback,
                )

                analises_batch: list[tuple[str, str, int]] = []
                for res in resultados:
                    id_vaga = res.get("id")
                    if not isinstance(id_vaga, int) or id_vaga < 0 or id_vaga >= len(vagas_para_analisar):
                        continue

                    compativel = res.get("compativel") is True
                    profissoes_match = [str(p).lower().strip() for p in res.get("profissoes_match", [])]
                    vaga_original = vagas_para_analisar[id_vaga]

                    for prof in profissoes:
                        is_match = 1 if compativel and (
                            prof.lower() in profissoes_match or len(profissoes) == 1
                        ) else 0
                        analises_batch.append((vaga_original["link"], prof, is_match))

                    if compativel:
                        vagas_compativeis.append(vaga_original)

                db.salvar_analises_filtro_batch(conn, analises_batch)
                conn.commit()

            except RuntimeError as e:
                logger.error(f"  ✗ Filtro detalhado falhou: {e}")
                cb.on_toast("⚠️ Erro ao analisar com IA. Alguns editais podem ter sido ignorados.")

            if i + LOTE_FILTRO < len(vagas_para_analisar):
                time.sleep(MODELOS_FILTRO[0]["pausa"])

            cb.on_progress(lote_num / total_lotes)

        cb.on_done()
        logger.info(f"✅ {len(vagas_compativeis)} vagas compatíveis encontradas")
        return vagas_compativeis

    finally:
        conn.close()


# ==========================================
# ETAPA 4: ANÁLISE DE CURRÍCULO
# ==========================================
def analisar_curriculo(texto_curriculo: str, vagas: list[dict], api_key: str,
                       cb: PipelineCallbacks = _EMPTY_CB) -> list[dict]:
    """Cruza o currículo com cada vaga, dando uma porcentagem de compatibilidade."""
    if not vagas:
        return []

    cv_hash = hashlib.sha256(texto_curriculo.encode("utf-8")).hexdigest()[:32]

    conn = db.get_connection()
    try:
        links_vagas = [v["link"] for v in vagas]
        cache_cv = db.buscar_cache_cv(conn, cv_hash, links_vagas)

        resultados: list[dict] = []
        vagas_para_analisar: list[dict] = []

        for vaga in vagas:
            link = vaga["link"]
            if link in cache_cv:
                vaga_cacheada = vaga.copy()
                vaga_cacheada.update(cache_cv[link])
                resultados.append(vaga_cacheada)
            else:
                vagas_para_analisar.append(vaga)

        logger.info(f"  ⚡ {len(resultados)} do cache, {len(vagas_para_analisar)} para analisar")

        if not vagas_para_analisar:
            cb.on_toast("⚡ Resultados resgatados do cache! (0 requisições novas à API)")
            return sorted(resultados, key=lambda x: x.get("porcentagem", 0), reverse=True)

        cb.on_info(f"🔬 Analisando {len(vagas_para_analisar)} editais com seu currículo...")

        client = ai_engine.get_client(api_key)
        total_lotes = (len(vagas_para_analisar) + LOTE_CV - 1) // LOTE_CV

        # System instruction com o currículo (enviado uma vez, não repetido a cada lote)
        system_cv = f"Você é um avançado sistema de ATS. Abaixo está o currículo do candidato:\n---\n{texto_curriculo}\n---"

        for i_batch in range(0, len(vagas_para_analisar), LOTE_CV):
            lote_num = (i_batch // LOTE_CV) + 1
            lote = vagas_para_analisar[i_batch:i_batch + LOTE_CV]

            cb.on_status(f"**🔬 Baixando e analisando PDFs (Lote {lote_num}/{total_lotes})**")
            logger.info(f"  🔬 Analisando CV: lote {lote_num}/{total_lotes}")

            # Monta texto das vagas com extração de PDF
            vagas_texto = "Analise os EDITAIS OFICIAIS das seguintes vagas:\n"
            for j, vaga in enumerate(lote):
                texto_edital = pdf_utils.extrair_texto_edital_pdf(vaga["link"], conn)
                if not texto_edital:
                    texto_edital = vaga.get("descricao_resumida", "Descrição indisponível.")
                vagas_texto += f"\n--- VAGA ID {j}: {vaga['orgao']} - {vaga['cargo']} ---\n{texto_edital[:MAX_CHARS_POR_EDITAL]}\n"

            prompt = PROMPT_CV.format(vagas_texto=vagas_texto)

            try:
                res_json = ai_engine.chamar_gemini_com_retry(
                    client, prompt, MODELOS_CV,
                    on_fallback=cb.on_fallback,
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

                conn.commit()

            except RuntimeError as e:
                logger.error(f"  ✗ Análise de CV falhou: {e}")
                cb.on_toast("⚠️ Erro ao analisar com IA. Alguns editais podem ter sido ignorados.")

            cb.on_progress(min((i_batch + LOTE_CV) / len(vagas_para_analisar), 1.0))
            if i_batch + LOTE_CV < len(vagas_para_analisar):
                time.sleep(MODELOS_CV[0]["pausa"])

        cb.on_done()
        return sorted(resultados, key=lambda x: x.get("porcentagem", 0), reverse=True)

    finally:
        conn.close()
