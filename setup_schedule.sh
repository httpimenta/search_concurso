#!/bin/bash
# ──────────────────────────────────────────────
# setup_schedule.sh
# Configura o agendamento diário via launchd (macOS)
# para executar a busca de concursos automaticamente.
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="$(which python3)"
PLIST_NAME="com.joaopimenta.cacador-concursos"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="${SCRIPT_DIR}/logs"
CONFIG_FILE="${SCRIPT_DIR}/config_diaria.json"

# Ler horário do config_diaria.json (default: 9)
HORA=9
if [ -f "${CONFIG_FILE}" ]; then
    hora_config=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}')).get('horario', 9))" 2>/dev/null)
    if [ -n "${hora_config}" ]; then
        HORA=${hora_config}
    fi
fi

echo "🎯 Configurando busca diária de concursos com IA"
echo "=================================================="
echo ""
echo "📍 Diretório do script: ${SCRIPT_DIR}"
echo "🐍 Python: ${PYTHON_PATH}"
echo "📋 Plist: ${PLIST_PATH}"
echo "⏰ Horário: ${HORA}:00"
echo ""

# Verificar se Python existe
if [ ! -f "${PYTHON_PATH}" ]; then
    echo "❌ Python3 não encontrado em: ${PYTHON_PATH}"
    echo "   Instale o Python3 ou ajuste o PATH."
    exit 1
fi

# Criar diretórios necessários
mkdir -p "${LOG_DIR}"
mkdir -p "${SCRIPT_DIR}/resultados"
mkdir -p "${SCRIPT_DIR}/data"

# Gerar o plist
cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SCRIPT_DIR}/busca_diaria.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <!-- Executa diariamente no horário configurado -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${HORA}</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Logs -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd_stderr.log</string>

    <!-- Variáveis de ambiente -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "✅ Arquivo plist criado em: ${PLIST_PATH}"
echo ""

# Descarregar se já existir
launchctl list | grep -q "${PLIST_NAME}" && {
    echo "⏳ Descarregando agendamento anterior..."
    launchctl unload "${PLIST_PATH}" 2>/dev/null
}

# Carregar o novo agendamento
echo "⏳ Carregando novo agendamento..."
launchctl load "${PLIST_PATH}"

if launchctl list | grep -q "${PLIST_NAME}"; then
    echo "✅ Agendamento carregado com sucesso!"
    echo ""
    echo "📅 O script será executado diariamente às ${HORA}:00."
    echo "📄 Logs em: ${LOG_DIR}/"
    echo "📊 Relatórios em: ${SCRIPT_DIR}/resultados/"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Comandos úteis:"
    echo "  Executar agora:       python3 ${SCRIPT_DIR}/busca_diaria.py"
    echo "  Ver status:           launchctl list | grep ${PLIST_NAME}"
    echo "  Desativar:            launchctl unload ${PLIST_PATH}"
    echo "  Reativar:             launchctl load ${PLIST_PATH}"
    echo "  Ver último relatório: open ${SCRIPT_DIR}/resultados/concursos_latest.html"
    echo "  Ver logs:             tail -f ${LOG_DIR}/busca_diaria.log"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "❌ Erro ao carregar o agendamento. Verifique o plist."
    exit 1
fi
