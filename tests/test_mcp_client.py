"""Testes para src/mcp_client.py — parsing da estrutura real da API."""
import pytest
from src.mcp_client import _extrair_data, parse_vagas
from src.models import Vaga


class TestExtrairData:
    """Testes para a extração de dados do envelope JSON-RPC."""

    def test_envelope_jsonrpc_padrao(self):
        """Estrutura real da API: result → content → text → JSON com data[]."""
        import json
        dados_internos = {
            "meta": {"total": 2},
            "data": [
                {"id": 1, "titulo": "Prefeitura A"},
                {"id": 2, "titulo": "Prefeitura B"},
            ],
        }
        resposta = {
            "result": {
                "content": [{"text": json.dumps(dados_internos)}]
            }
        }
        resultado = _extrair_data(resposta)
        assert len(resultado) == 2
        assert resultado[0]["titulo"] == "Prefeitura A"

    def test_resposta_direta_com_data(self):
        """Fallback: resposta direta com campo data."""
        resposta = {
            "data": [{"id": 1, "titulo": "Câmara X"}]
        }
        resultado = _extrair_data(resposta)
        assert len(resultado) == 1

    def test_lista_direta(self):
        """Fallback: resposta é diretamente uma lista."""
        resposta = [{"id": 1, "titulo": "Órgão Y"}]
        resultado = _extrair_data(resposta)
        assert len(resultado) == 1

    def test_resposta_vazia(self):
        """Resposta sem dados retorna lista vazia."""
        assert _extrair_data({}) == []
        assert _extrair_data({"result": {}}) == []

    def test_content_texto_invalido(self):
        """Se o text dentro de content não é JSON válido, retorna vazio."""
        resposta = {
            "result": {"content": [{"text": "isso não é json"}]}
        }
        resultado = _extrair_data(resposta)
        assert resultado == []


class TestParseVagas:
    """Testes para a conversão de dicts da API em objetos Vaga."""

    def test_parse_vaga_completa(self):
        """Parseia uma vaga completa com todos os campos."""
        dados = [{
            "id": 291080,
            "titulo": "Câmara de Arujá",
            "cargos_resumo": "Vários Cargos",
            "cargos": ["ANALISTA JURÍDICO", "WEB DESIGNER LEGISLATIVO"],
            "vagas_salario": "5 vagas até R$ 15.659,70",
            "formacao": "Médio / Técnico / Superior",
            "regiao": "SUDESTE",
            "uf": "SP",
            "datas": {
                "inicio": "2026-04-27",
                "fim": "2026-07-13",
                "texto": "",
                "aberto": True,
                "dias_restantes": 32,
            },
            "noticia": {
                "id": 291080,
                "titulo": "Câmara de Arujá - SP retifica concurso",
                "link": "https://www.pciconcursos.com.br/noticias/camara-de-aruja",
                "imagem": "https://cdn.pci.app.br/img/test.png",
            },
        }]

        vagas = parse_vagas(dados)
        assert len(vagas) == 1

        vaga = vagas[0]
        assert vaga.id == 291080
        assert vaga.orgao == "Câmara de Arujá"
        assert vaga.link == "https://www.pciconcursos.com.br/noticias/camara-de-aruja"
        assert vaga.datas.aberto is True
        assert vaga.datas.dias_restantes == 32
        assert "ANALISTA JURÍDICO" in vaga.cargos
        assert "WEB DESIGNER LEGISLATIVO" in vaga.cargos
        assert vaga.uf == "SP"

    def test_parse_vaga_sem_noticia(self):
        """Vaga sem notícia deve ter link vazio mas não dar erro."""
        dados = [{"id": 1, "titulo": "Org X"}]
        vagas = parse_vagas(dados)
        assert len(vagas) == 1
        assert vagas[0].link == ""

    def test_parse_vaga_encerrada(self):
        """Vaga com datas.aberto=false deve ser parseada corretamente."""
        dados = [{
            "id": 1, "titulo": "Org Y",
            "datas": {"aberto": False, "dias_restantes": -5},
            "noticia": {"link": "https://exemplo.com"},
        }]
        vagas = parse_vagas(dados)
        assert vagas[0].datas.aberto is False
        assert vagas[0].datas.dias_restantes == -5

    def test_parse_lista_vazia(self):
        """Lista vazia retorna lista vazia."""
        assert parse_vagas([]) == []

    def test_propriedade_cargo_formatado(self):
        """A propriedade cargo retorna os cargos como string."""
        dados = [{"id": 1, "titulo": "X", "cargos": ["A", "B", "C"]}]
        vagas = parse_vagas(dados)
        assert vagas[0].cargo == "A, B, C"

    def test_propriedade_cargo_sem_lista(self):
        """Sem lista de cargos, usa cargos_resumo."""
        dados = [{"id": 1, "titulo": "X", "cargos_resumo": "Vários Cargos"}]
        vagas = parse_vagas(dados)
        assert vagas[0].cargo == "Vários Cargos"
