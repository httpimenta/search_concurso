# 🎯 Caçador de Concursos com IA (V2)

Aplicação Streamlit que busca concursos públicos brasileiros via **MCP (Model Context Protocol)** do [PCI Concursos](https://www.pciconcursos.com.br), filtra vagas usando **Gemini IA** e analisa a compatibilidade com seu currículo.

## ✨ Funcionalidades

- **Busca inteligente** por região, cargo ou cidade
- **Filtro por senioridade** — Júnior/Pleno/Sênior/Estágio (opcional) por área, inferida pela IA a partir dos requisitos do edital
- **Pente Fino com IA** — filtra automaticamente cargos irrelevantes
- **Análise de Currículo** — cruza seu PDF com os editais e dá um ranking de compatibilidade
- **Cache SQLite** — não reprocessa vagas já analisadas
- **Extração de editais PDF** — lê editais diretamente dos PDFs oficiais
- **Busca diária automatizada** — pipeline headless com relatório HTML, ativável pelo próprio app
- **Agendamento multiplataforma** — detecta o SO e agenda via launchd (macOS), Agendador de Tarefas (Windows) ou cron (Linux)
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
├── busca_diaria.py            # Pipeline headless para execução agendada
├── config_diaria.json         # Configuração da busca diária (profissões, regiões)
├── setup_schedule.sh          # Script de agendamento via launchd (macOS)
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
│   ├── pdf_utils.py           # Extração de texto de PDFs
│   ├── pipeline.py            # Pipeline central de negócios (pente fino, filtro, CV)
│   ├── prompts.py             # Prompts centralizados para o Gemini
│   ├── report.py              # Gerador de relatórios HTML
│   ├── scheduler.py           # Agendamento multiplataforma (launchd/schtasks/cron)
│   └── styles.py              # Componentes CSS para o Streamlit
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
├── resultados/                # Relatórios HTML da busca diária
└── old/                       # Versões anteriores (arquivo)
```

## 🧪 Testes

```bash
python -m pytest tests/ -v
```

## ⏰ Busca Diária Automatizada

O projeto inclui um pipeline headless (`busca_diaria.py`) que roda diariamente e gera um relatório HTML. Os relatórios são salvos em `resultados/`, com `concursos_latest.html` apontando para o mais recente.

### Ativar pelo app (recomendado)

Na **sidebar** do app, seção **🤖 Busca Diária Automática**, há um interruptor para ativar/desativar e escolher o horário. O app detecta o sistema operacional e agenda automaticamente no agendador nativo:

| Sistema | Agendador |
|---|---|
| macOS | `launchd` (LaunchAgent em `~/Library/LaunchAgents/`) |
| Windows | Agendador de Tarefas (`schtasks`) |
| Linux | `cron` |

### Configuração

O arquivo `config_diaria.json` guarda as preferências (também editável à mão):

```json
{
  "ativa": true,
  "profissoes": ["UX Designer (Júnior)", "Product Designer (Júnior)"],
  "regioes": ["", "sudeste"],
  "analisar_curriculo": true,
  "horario": 9
}
```

| Campo | Descrição |
|---|---|
| `ativa` | Liga/desliga a busca diária (o script não roda se `false`) |
| `profissoes` | Áreas para filtrar; senioridade opcional entre parênteses, ex: `"UX Designer (Sênior)"` |
| `regioes` | Regiões para buscar (`""` = Nacional) |
| `analisar_curriculo` | Se `true`, cruza o CV mais recente com as vagas |
| `horario` | Hora do dia para executar (0-23) |

### Executar manualmente

```bash
python busca_diaria.py
```

### Agendar por linha de comando (macOS, alternativa)

```bash
chmod +x setup_schedule.sh
./setup_schedule.sh
```

Usa o mesmo `LaunchAgent` que o toggle do app, então não há conflito entre os dois.

## ⚠️ Segurança

- **NUNCA** suba o arquivo `.streamlit/secrets.toml` para o repositório
- O `.gitignore` já está configurado para ignorar secrets, bancos e logs
- Se hospedar no Streamlit Cloud, configure a chave nas **Settings > Secrets** do painel web
