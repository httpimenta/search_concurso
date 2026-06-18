"""Testes para src/ai_engine.py — parsing de JSON e limpeza de respostas."""
import pytest
from src.ai_engine import limpar_json_resposta


class TestLimparJsonResposta:
    """Testes para a função limpar_json_resposta."""

    def test_json_limpo_passthrough(self):
        """JSON puro sem fences deve ser retornado intacto."""
        entrada = '[{"id": 0, "relevante": true}]'
        assert limpar_json_resposta(entrada) == entrada

    def test_json_com_fences_code(self):
        """Remove ```json ... ``` e extrai o conteúdo."""
        entrada = '```json\n[{"id": 0, "relevante": true}]\n```'
        resultado = limpar_json_resposta(entrada)
        assert resultado == '[{"id": 0, "relevante": true}]'

    def test_json_com_fences_simples(self):
        """Remove ``` ... ``` sem especificador de linguagem."""
        entrada = '```\n[{"id": 0}]\n```'
        resultado = limpar_json_resposta(entrada)
        assert resultado == '[{"id": 0}]'

    def test_json_com_texto_antes(self):
        """Extrai array JSON mesmo com texto antes dele."""
        entrada = 'Aqui está o resultado:\n[{"id": 0}]'
        resultado = limpar_json_resposta(entrada)
        assert resultado == '[{"id": 0}]'

    def test_json_com_texto_antes_e_depois(self):
        """Extrai array JSON com texto antes e depois."""
        entrada = 'Resultado:\n[{"id": 0, "ok": true}]\nFim da análise.'
        resultado = limpar_json_resposta(entrada)
        assert resultado == '[{"id": 0, "ok": true}]'

    def test_json_objeto_unico(self):
        """Extrai um objeto JSON (não array)."""
        entrada = '{"status": "ok"}'
        resultado = limpar_json_resposta(entrada)
        assert resultado == '{"status": "ok"}'

    def test_fences_com_json_e_texto_misto(self):
        """Cenário mais complexo: fences + texto + JSON interno."""
        entrada = '```json\nAqui estão os resultados:\n[{"id": 1, "compativel": false}]\n```'
        resultado = limpar_json_resposta(entrada)
        assert resultado == '[{"id": 1, "compativel": false}]'

    def test_string_vazia(self):
        """String vazia retorna vazia."""
        assert limpar_json_resposta("") == ""

    def test_texto_sem_json(self):
        """Texto sem JSON retorna o próprio texto (stripped)."""
        entrada = "Não encontrei resultados relevantes."
        resultado = limpar_json_resposta(entrada)
        assert resultado == entrada
