"""
Agendamento multiplataforma da busca diária.

Detecta o sistema operacional e usa o agendador nativo:
  - macOS   → launchd  (mesmo label/plist do setup_schedule.sh, gerencia o mesmo job)
  - Windows → Agendador de Tarefas (schtasks)
  - Linux   → cron

API pública:
  detectar_sistema() -> str
  nome_sistema() -> str
  status_agendamento() -> bool
  instalar_agendamento(hora: int) -> tuple[bool, str]
  remover_agendamento() -> tuple[bool, str]
"""
from __future__ import annotations
import os
import sys
import subprocess
import logging

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Identificadores compartilhados com setup_schedule.sh — no macOS, gerenciam o MESMO job.
LABEL = "com.joaopimenta.cacador-concursos"
TAREFA_WINDOWS = "CacadorConcursosBuscaDiaria"
MARCADOR_CRON = "# cacador-concursos-busca-diaria"

SCRIPT = os.path.join(PROJECT_ROOT, "busca_diaria.py")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


# ==========================================
# DETECÇÃO DE SISTEMA
# ==========================================
def detectar_sistema() -> str:
    """Retorna 'macos', 'windows', 'linux' ou 'desconhecido'."""
    p = sys.platform
    if p == "darwin":
        return "macos"
    if p.startswith("win"):
        return "windows"
    if p.startswith("linux"):
        return "linux"
    return "desconhecido"


def nome_sistema() -> str:
    """Nome amigável do agendador usado neste sistema."""
    return {
        "macos": "macOS · launchd",
        "windows": "Windows · Agendador de Tarefas",
        "linux": "Linux · cron",
    }.get(detectar_sistema(), "Sistema não suportado")


def _python_executavel() -> str:
    """
    Caminho do interpretador a usar no agendamento.
    No Windows, prefere pythonw.exe (sem janela de console).
    """
    exe = sys.executable or "python3"
    if detectar_sistema() == "windows":
        base = os.path.basename(exe).lower()
        if base == "python.exe":
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.exists(pyw):
                return pyw
    return exe


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Executa um comando capturando saída, sem levantar exceção em rc != 0."""
    logger.info(f"scheduler: executando {' '.join(args)}")
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


# ==========================================
# macOS (launchd)
# ==========================================
def _plist_conteudo(hora: int) -> str:
    python = _python_executavel()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hora}</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{LOG_DIR}/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/launchd_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
"""


def _dominio_macos() -> str:
    """Domínio do usuário logado na sessão gráfica (Aqua)."""
    return f"gui/{os.getuid()}"


def _instalar_macos(hora: int) -> tuple[bool, str]:
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(PLIST_PATH, "w", encoding="utf-8") as f:
        f.write(_plist_conteudo(hora))

    dominio = _dominio_macos()
    # Remove versão anterior (ignora erro se não estiver carregado)
    _run(["launchctl", "bootout", dominio, PLIST_PATH])
    # API moderna (macOS 11+); recai no load legado se indisponível
    r = _run(["launchctl", "bootstrap", dominio, PLIST_PATH])
    if r.returncode != 0:
        _run(["launchctl", "load", "-w", PLIST_PATH])
    _run(["launchctl", "enable", f"{dominio}/{LABEL}"])  # garante habilitado

    if _status_macos():
        return True, f"Agendado no launchd para rodar todo dia às {hora}h."
    return False, f"launchd não confirmou o registro: {r.stderr.strip() or 'erro desconhecido'}"


def _remover_macos() -> tuple[bool, str]:
    if os.path.exists(PLIST_PATH):
        _run(["launchctl", "bootout", _dominio_macos(), PLIST_PATH])
        _run(["launchctl", "unload", PLIST_PATH])  # fallback legado
        os.remove(PLIST_PATH)
    return True, "Agendamento removido do launchd."


def _status_macos() -> bool:
    if not os.path.exists(PLIST_PATH):
        return False
    # Domain-explicit (confiável e independente do contexto do chamador)
    if _run(["launchctl", "print", f"{_dominio_macos()}/{LABEL}"]).returncode == 0:
        return True
    return LABEL in _run(["launchctl", "list"]).stdout  # fallback legado


# ==========================================
# Windows (schtasks)
# ==========================================
def _instalar_windows(hora: int) -> tuple[bool, str]:
    comando = f'"{_python_executavel()}" "{SCRIPT}"'
    r = _run([
        "schtasks", "/Create", "/TN", TAREFA_WINDOWS,
        "/SC", "DAILY", "/ST", f"{hora:02d}:00",
        "/TR", comando, "/F",
    ])
    if r.returncode != 0:
        return False, f"Falha no schtasks: {r.stderr.strip() or r.stdout.strip()}"
    return True, f"Tarefa agendada no Windows para rodar todo dia às {hora}h."


def _remover_windows() -> tuple[bool, str]:
    _run(["schtasks", "/Delete", "/TN", TAREFA_WINDOWS, "/F"])  # rc!=0 se não existir → ok
    return True, "Tarefa removida do Agendador de Tarefas do Windows."


def _status_windows() -> bool:
    return _run(["schtasks", "/Query", "/TN", TAREFA_WINDOWS]).returncode == 0


# ==========================================
# Linux (cron)
# ==========================================
def _ler_crontab() -> str:
    r = _run(["crontab", "-l"])
    return r.stdout if r.returncode == 0 else ""


def _linhas_sem_marcador(texto: str) -> list[str]:
    return [l for l in texto.splitlines() if MARCADOR_CRON not in l and l.strip()]


def _escrever_crontab(linhas: list[str]) -> tuple[bool, str]:
    conteudo = "\n".join(linhas).strip() + "\n"
    p = subprocess.run(["crontab", "-"], input=conteudo, text=True, capture_output=True)
    return p.returncode == 0, p.stderr.strip()


def _instalar_linux(hora: int) -> tuple[bool, str]:
    os.makedirs(LOG_DIR, exist_ok=True)
    linhas = _linhas_sem_marcador(_ler_crontab())
    linha = (
        f"0 {hora} * * * cd '{PROJECT_ROOT}' && "
        f"'{_python_executavel()}' busca_diaria.py >> '{LOG_DIR}/cron.log' 2>&1 {MARCADOR_CRON}"
    )
    linhas.append(linha)
    ok, err = _escrever_crontab(linhas)
    if not ok:
        return False, f"Falha ao escrever crontab: {err or 'erro desconhecido'}"
    return True, f"Agendado no cron para rodar todo dia às {hora}h."


def _remover_linux() -> tuple[bool, str]:
    linhas = _linhas_sem_marcador(_ler_crontab())
    ok, err = _escrever_crontab(linhas)
    if not ok:
        return False, f"Falha ao atualizar crontab: {err or 'erro desconhecido'}"
    return True, "Agendamento removido do cron."


def _status_linux() -> bool:
    return MARCADOR_CRON in _ler_crontab()


# ==========================================
# DISPATCH
# ==========================================
def instalar_agendamento(hora: int) -> tuple[bool, str]:
    """Cria/atualiza o agendamento diário no horário dado. Retorna (sucesso, mensagem)."""
    hora = max(0, min(23, int(hora)))
    sistema = detectar_sistema()
    try:
        if sistema == "macos":
            return _instalar_macos(hora)
        if sistema == "windows":
            return _instalar_windows(hora)
        if sistema == "linux":
            return _instalar_linux(hora)
    except Exception as e:
        logger.exception("Erro ao instalar agendamento")
        return False, f"Erro ao agendar: {e}"
    return False, "Agendamento automático não é suportado neste sistema."


def remover_agendamento() -> tuple[bool, str]:
    """Remove o agendamento diário. Retorna (sucesso, mensagem)."""
    sistema = detectar_sistema()
    try:
        if sistema == "macos":
            return _remover_macos()
        if sistema == "windows":
            return _remover_windows()
        if sistema == "linux":
            return _remover_linux()
    except Exception as e:
        logger.exception("Erro ao remover agendamento")
        return False, f"Erro ao remover agendamento: {e}"
    return False, "Agendamento automático não é suportado neste sistema."


def status_agendamento() -> bool:
    """True se o agendamento diário está instalado no sistema."""
    sistema = detectar_sistema()
    try:
        if sistema == "macos":
            return _status_macos()
        if sistema == "windows":
            return _status_windows()
        if sistema == "linux":
            return _status_linux()
    except Exception:
        logger.exception("Erro ao consultar status do agendamento")
    return False
