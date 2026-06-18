# 🎯 Caçador de Concursos com IA (V2)

Aplicação Streamlit que busca concursos públicos brasileiros via **MCP (Model Context Protocol)** do [PCI Concursos](https://www.pciconcursos.com.br), filtra vagas usando **Gemini IA** e analisa a compatibilidade com seu currículo.

## ✨ Funcionalidades

- **Busca inteligente** por região, cargo ou cidade
- **Pente Fino com IA** — filtra automaticamente cargos irrelevantes
- **Análise de Currículo** — cruza seu PDF com os editais e dá um ranking de compatibilidade
- **Cache SQLite** — não reprocessa vagas já analisadas
- **Extração de editais PDF** — lê editais diretamente dos PDFs oficiais
- **Laboratório de testes** — inspeciona dados brutos da API e testa extração de CV

## 📋 Pré-requisitos

- Python 3.10+
- Chave de API do Google Gemini ([obter aqui](https://aistudio.google.com/apikey))

## 🚀 Instalação

```bash
# 1. Clone o repositório
git clone <url-do-repo>
cd search_concurso

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure a chave da API
mkdir -p .streamlit
echo 'GEMINI_API_KEY = "sua_chave_aqui"' > .streamlit/secrets.toml
```

## ▶️ Como rodar

```bash
streamlit run app_v2.py
```

A aplicação abrirá em `http://localhost:8501`.

## 📁 Estrutura do Projeto

```
search_concurso/
├── app_v2.py                  # Aplicação principal (UI Streamlit)
├── requirements.txt           # Dependências Python
├── .gitignore
│
├── src/                       # Módulos do backend
│   ├── __init__.py
│   ├── config.py              # Constantes, API key, logging
│   ├── models.py              # Dataclasses tipadas (Vaga, Datas, etc.)
│   ├── db.py                  # Banco de dados SQLite (CRUD, migrações)
│   ├── ai_engine.py           # Motor de IA (Gemini, retry, parsing JSON)
│   ├── mcp_client.py          # Cliente MCP (comunicação com PCI Concursos)
│   └── pdf_utils.py           # Extração de texto de PDFs
│
├── pages/                     # Páginas secundárias do Streamlit
│   ├── 1_Banco_de_Dados.py    # Gestão e exportação de vagas
│   └── 2_Laboratorio.py       # Testes de CV, explorador MCP, modelos
│
├── tests/                     # Testes automatizados
│   ├── test_ai_engine.py
│   ├── test_db.py
│   └── test_mcp_client.py
│
├── data/                      # Banco SQLite (gerado automaticamente)
├── logs/                      # Logs de execução (gerados automaticamente)
└── old/                       # Versões anteriores (arquivo)
```

## 🧪 Testes

```bash
python -m pytest tests/ -v
```

## ⚠️ Segurança

- **NUNCA** suba o arquivo `.streamlit/secrets.toml` para o repositório
- O `.gitignore` já está configurado para ignorar secrets, bancos e logs
- Se hospedar no Streamlit Cloud, configure a chave nas **Settings > Secrets** do painel web
