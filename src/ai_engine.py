"""
Motor de Inteligência Artificial — chamadas ao Gemini com retry e parsing de JSON.
Elimina toda a duplicação de lógica de retry/fallback que existia em 4+ lugares.
"""
from __future__ import annotations
import json
import time
import logging
from typing import Any, Callable
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def get_client(api_key: str) -> genai.Client:
    """Cria e retorna um client Gemini validado."""
    return genai.Client(api_key=api_key)


def limpar_json_resposta(texto: str) -> str:
    """
    Remove markdown fences e extrai o array/objeto JSON de uma resposta da IA.
    Lida com: ```json ... ```, texto antes/depois do JSON, etc.
    """
    resposta = texto.strip()

    # Remove fences de código
    if resposta.startswith("```json"):
        resposta = resposta[7:]
    elif resposta.startswith("```"):
        resposta = resposta[3:]
    if resposta.endswith("```"):
        resposta = resposta[:-3]

    resposta = resposta.strip()

    # Encontra o array JSON mais externo
    inicio_arr = resposta.find("[")
    inicio_obj = resposta.find("{")

    if inicio_arr != -1:
        fim = resposta.rfind("]") + 1
        if fim > 0:
            return resposta[inicio_arr:fim]
    elif inicio_obj != -1:
        fim = resposta.rfind("}") + 1
        if fim > 0:
            return resposta[inicio_obj:fim]

    return resposta


def chamar_gemini_com_retry(
    client: genai.Client,
    prompt: str,
    modelos: list[dict],
    parse_json: bool = True,
    on_fallback: Callable[[str, str], None] | None = None,
    system_instruction: str | None = None,
) -> Any:
    """
    Chama a Gemini API com retry automático e fallback entre modelos.

    Args:
        client: Client Gemini autenticado
        prompt: O prompt a enviar
        modelos: Lista de dicts com 'nome' e 'pausa' (ex: [{"nome": "gemini-flash-latest", "pausa": 15}])
        parse_json: Se True, faz parsing do JSON da resposta
        on_fallback: Callback(modelo_antigo, modelo_novo) quando trocar de modelo
        system_instruction: Instrução de sistema opcional

    Returns:
        Resultado parseado (list/dict se parse_json=True, str se False)

    Raises:
        RuntimeError: Se todos os modelos e tentativas falharem
    """
    modelo_idx = 0
    ultimo_erro = None

    while modelo_idx < len(modelos):
        modelo_atual = modelos[modelo_idx]
        tentativas_restantes = 2

        while tentativas_restantes > 0:
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json" if parse_json else "text/plain",
                    system_instruction=system_instruction,
                )

                resposta = client.models.generate_content(
                    model=modelo_atual["nome"],
                    contents=prompt,
                    config=config,
                ).text

                if parse_json:
                    resposta_limpa = limpar_json_resposta(resposta)
                    return json.loads(resposta_limpa)
                return resposta

            except Exception as e:
                ultimo_erro = e
                erro_str = str(e)
                logger.warning(f"Erro com {modelo_atual['nome']}: {erro_str[:200]}")

                # Cota diária esgotada → próximo modelo
                if "429" in erro_str and ("PerDay" in erro_str or "Quota exceeded" in erro_str):
                    old_name = modelo_atual["nome"]
                    modelo_idx += 1
                    if modelo_idx < len(modelos) and on_fallback:
                        on_fallback(old_name, modelos[modelo_idx]["nome"])
                    break  # Sai do while interno, continua no while externo

                # Servidor sobrecarregado (503/500)
                elif "503" in erro_str or "500" in erro_str:
                    tentativas_restantes -= 1
                    if tentativas_restantes > 0:
                        time.sleep(60)
                    elif modelo_idx < len(modelos) - 1:
                        old_name = modelo_atual["nome"]
                        modelo_idx += 1
                        if on_fallback:
                            on_fallback(old_name, modelos[modelo_idx]["nome"])
                        break

                # Rate limit (429 simples)
                elif "429" in erro_str:
                    tentativas_restantes -= 1
                    if tentativas_restantes > 0:
                        time.sleep(60)

                # Modelo não existe (404)
                elif "404" in erro_str:
                    old_name = modelo_atual["nome"]
                    modelo_idx += 1
                    if modelo_idx < len(modelos) and on_fallback:
                        on_fallback(old_name, modelos[modelo_idx]["nome"])
                    break

                # JSON inválido da IA
                elif "JSONDecodeError" in type(e).__name__ or "Expecting" in erro_str:
                    tentativas_restantes -= 1
                    if tentativas_restantes > 0:
                        time.sleep(2)
                    elif modelo_idx < len(modelos) - 1:
                        old_name = modelo_atual["nome"]
                        modelo_idx += 1
                        if on_fallback:
                            on_fallback(old_name, modelos[modelo_idx]["nome"])
                        break

                # Erro desconhecido
                else:
                    logger.error(f"Erro desconhecido com {modelo_atual['nome']}: {erro_str[:300]}")
                    tentativas_restantes -= 1
                    if tentativas_restantes <= 0 and modelo_idx < len(modelos) - 1:
                        old_name = modelo_atual["nome"]
                        modelo_idx += 1
                        if on_fallback:
                            on_fallback(old_name, modelos[modelo_idx]["nome"])
                        break
        else:
            # while interno terminou normalmente (todas as tentativas esgotadas)
            modelo_idx += 1

    raise RuntimeError(f"Todos os modelos falharam. Último erro: {ultimo_erro}")
