"""
Camada de acesso ao banco de dados SQLite.
Centraliza conexões, migrações e todas as queries do projeto.

Convenção de commits:
  - Funções de ação unitária (ex: atualizar_inscricao, limpar_cache_ia) fazem commit interno.
  - Funções de lote/batch NÃO fazem commit — o chamador (pipeline) controla a transação.
"""
from __future__ import annotations
import os
import sqlite3
import json
import logging
from src.config import DB_PATH

logger = logging.getLogger(__name__)

# Conjunto de caminhos já migrados nesta execução (evita re-migrar a cada conexão)
_migrated_paths: set[str] = set()


# ==========================================
# CONEXÃO
# ==========================================
def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Retorna uma conexão SQLite com WAL mode habilitado.
    Executa migrações automaticamente na primeira conexão por caminho.
    IMPORTANTE: sempre use try/finally para garantir conn.close().
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")

    abs_path = os.path.abspath(db_path)
    if abs_path not in _migrated_paths:
        migrate(conn)
        _migrated_paths.add(abs_path)

    return conn


# ==========================================
# MIGRAÇÕES
# ==========================================
MIGRATIONS = [
    # V1 — Schema inicial
    """
    CREATE TABLE IF NOT EXISTS vagas (
        link TEXT PRIMARY KEY,
        orgao TEXT,
        cargo TEXT,
        descricao_resumida TEXT,
        status TEXT DEFAULT 'aberto',
        inscrito INTEGER DEFAULT 0,
        data_encerramento TEXT DEFAULT 'Não informada',
        texto_completo INTEGER DEFAULT 0,
        salario TEXT DEFAULT '',
        formacao TEXT DEFAULT '',
        regiao TEXT DEFAULT '',
        uf TEXT DEFAULT '',
        texto_edital TEXT DEFAULT NULL,
        dias_restantes INTEGER DEFAULT 0,
        datas_texto TEXT DEFAULT ''
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS analises_filtro (
        link TEXT,
        profissao TEXT,
        compativel INTEGER,
        PRIMARY KEY(link, profissao)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS analises_cv (
        cv_hash TEXT,
        link TEXT,
        porcentagem INTEGER,
        justificativa TEXT,
        habilidades_encontradas TEXT,
        habilidades_faltantes TEXT,
        PRIMARY KEY(cv_hash, link)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS curriculos_salvos (
        cv_hash TEXT PRIMARY KEY,
        nome_arquivo TEXT,
        data_upload TEXT,
        texto_extraido TEXT
    );
    """,
]


def migrate(conn: sqlite3.Connection) -> None:
    """
    Executa migrações incrementais usando tabela schema_version.
    Cada migração roda apenas uma vez.
    """
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """)
    c.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    current_version = c.fetchone()[0]

    for i, sql in enumerate(MIGRATIONS, start=1):
        if i > current_version:
            try:
                c.executescript(sql)
                c.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
                logger.info(f"Migração V{i} aplicada com sucesso.")
            except sqlite3.OperationalError as e:
                # Tabela/coluna já existe — ignora e marca como aplicada
                logger.warning(f"Migração V{i} ignorada (já existente): {e}")
                c.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (i,))

    # Adiciona colunas novas se não existirem (compatibilidade com bancos antigos)
    _ensure_columns(c)
    conn.commit()


def _ensure_columns(c: sqlite3.Cursor) -> None:
    """Garante que colunas adicionadas em versões posteriores existam."""
    colunas_extras = [
        ("vagas", "dias_restantes", "INTEGER DEFAULT 0"),
        ("vagas", "datas_texto", "TEXT DEFAULT ''"),
    ]
    for tabela, coluna, tipo in colunas_extras:
        try:
            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError:
            pass  # Coluna já existe


# ==========================================
# VAGAS — CRUD
# ==========================================
def salvar_vaga(conn: sqlite3.Connection, link: str, orgao: str, cargo: str,
                descricao: str, status: str, data_enc: str, salario: str,
                formacao: str, regiao: str, uf: str,
                dias_restantes: int = 0, datas_texto: str = "") -> bool:
    """Insere uma vaga no banco. Retorna True se foi inserida (nova). NÃO faz commit."""
    try:
        conn.execute(
            """INSERT INTO vagas
               (link, orgao, cargo, descricao_resumida, status, data_encerramento,
                texto_completo, salario, formacao, regiao, uf, dias_restantes, datas_texto)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)""",
            (link, orgao, cargo, descricao, status, data_enc,
             salario, formacao, regiao, uf, dias_restantes, datas_texto),
        )
        return True
    except sqlite3.IntegrityError:
        return False  # Link já existe


def buscar_links_salvos(conn: sqlite3.Connection) -> set[str]:
    """Retorna o conjunto de todos os links já salvos no banco."""
    c = conn.cursor()
    c.execute("SELECT link FROM vagas")
    return {row[0] for row in c.fetchall()}


def atualizar_status_vagas(conn: sqlite3.Connection, links_ativos: list[str],
                           links_encerrados: list[str]) -> None:
    """Atualiza o status aberto/encerrado das vagas baseado nos dados da API. NÃO faz commit."""
    c = conn.cursor()
    todos_links = links_ativos + links_encerrados

    if todos_links:
        placeholders = ",".join(["?"] * len(todos_links))
        c.execute(
            f"UPDATE vagas SET status = 'encerrado' WHERE link NOT IN ({placeholders})",
            tuple(todos_links),
        )

    if links_ativos:
        placeholders = ",".join(["?"] * len(links_ativos))
        c.execute(
            f"UPDATE vagas SET status = 'aberto' WHERE link IN ({placeholders})",
            tuple(links_ativos),
        )

    if links_encerrados:
        placeholders = ",".join(["?"] * len(links_encerrados))
        c.execute(
            f"UPDATE vagas SET status = 'encerrado' WHERE link IN ({placeholders})",
            tuple(links_encerrados),
        )


def buscar_vagas_abertas(conn: sqlite3.Connection) -> list[dict]:
    """Retorna todas as vagas com status 'aberto'."""
    c = conn.cursor()
    c.execute(
        """SELECT orgao, cargo, descricao_resumida, link, salario, formacao,
                  regiao, uf, dias_restantes, datas_texto
           FROM vagas WHERE status = 'aberto'"""
    )
    return [
        {
            "orgao": r[0], "cargo": r[1], "descricao_resumida": r[2],
            "link": r[3], "salario": r[4], "formacao": r[5],
            "regiao": r[6], "uf": r[7],
            "dias_restantes": r[8] if r[8] else 0,
            "datas_texto": r[9] if r[9] else "",
        }
        for r in c.fetchall()
    ]


def buscar_vagas_sem_texto(conn: sqlite3.Connection) -> list[dict]:
    """Retorna vagas abertas que ainda não tiveram o texto completo extraído."""
    c = conn.cursor()
    c.execute(
        """SELECT link, orgao, cargo, descricao_resumida
           FROM vagas WHERE status = 'aberto' AND texto_completo = 0"""
    )
    return [
        {"link": r[0], "orgao": r[1], "cargo": r[2], "descricao_resumida": r[3]}
        for r in c.fetchall()
    ]


def marcar_texto_extraido(conn: sqlite3.Connection, link: str, texto: str | None) -> None:
    """Marca uma vaga como tendo o texto completo extraído. NÃO faz commit."""
    if texto:
        conn.execute(
            "UPDATE vagas SET descricao_resumida = ?, texto_completo = 1 WHERE link = ?",
            (texto, link),
        )
    else:
        conn.execute("UPDATE vagas SET texto_completo = 1 WHERE link = ?", (link,))


# ==========================================
# CACHE DO FILTRO DE PROFISSÃO
# ==========================================
def buscar_cache_filtro(conn: sqlite3.Connection, profissoes: list[str]) -> dict[str, dict[str, bool]]:
    """
    Busca o cache de análises de filtro para as profissões dadas.
    Retorna: {link: {profissao: True/False, ...}, ...}
    """
    if not profissoes:
        return {}
    c = conn.cursor()
    placeholders = ",".join(["?"] * len(profissoes))
    c.execute(
        f"SELECT link, profissao, compativel FROM analises_filtro WHERE profissao IN ({placeholders})",
        tuple(profissoes),
    )
    cache: dict[str, dict[str, bool]] = {}
    for link, prof, compativel in c.fetchall():
        if link not in cache:
            cache[link] = {}
        cache[link][prof] = bool(compativel)
    return cache


def salvar_analise_filtro(conn: sqlite3.Connection, link: str, profissao: str,
                          compativel: int) -> None:
    """Salva (ou atualiza) o resultado de uma análise de filtro. NÃO faz commit."""
    conn.execute(
        "INSERT OR REPLACE INTO analises_filtro (link, profissao, compativel) VALUES (?, ?, ?)",
        (link, profissao, compativel),
    )


def salvar_analises_filtro_batch(conn: sqlite3.Connection,
                                 analises: list[tuple[str, str, int]]) -> None:
    """Salva múltiplas análises de filtro de uma vez (batch insert). NÃO faz commit."""
    conn.executemany(
        "INSERT OR REPLACE INTO analises_filtro (link, profissao, compativel) VALUES (?, ?, ?)",
        analises,
    )


def buscar_profissoes_salvas(conn: sqlite3.Connection) -> list[str]:
    """Retorna as profissões distintas que já foram analisadas."""
    c = conn.cursor()
    try:
        c.execute("SELECT DISTINCT profissao FROM analises_filtro")
        return sorted([row[0] for row in c.fetchall() if row[0]])
    except sqlite3.OperationalError:
        return []


# ==========================================
# CACHE DE ANÁLISE DE CURRÍCULO
# ==========================================
def buscar_cache_cv(conn: sqlite3.Connection, cv_hash: str,
                    links: list[str]) -> dict[str, dict]:
    """
    Busca análises já feitas para este currículo.
    Retorna: {link: {porcentagem, justificativa, habilidades_encontradas, habilidades_faltantes}}
    """
    if not links:
        return {}
    c = conn.cursor()
    placeholders = ",".join(["?"] * len(links))
    c.execute(
        f"""SELECT link, porcentagem, justificativa, habilidades_encontradas, habilidades_faltantes
            FROM analises_cv WHERE cv_hash = ? AND link IN ({placeholders})""",
        [cv_hash] + links,
    )
    cache: dict[str, dict] = {}
    for link, pct, just, hab_enc, hab_falt in c.fetchall():
        try:
            cache[link] = {
                "porcentagem": pct,
                "justificativa": just,
                "habilidades_encontradas": json.loads(hab_enc),
                "habilidades_faltantes": json.loads(hab_falt),
            }
        except (json.JSONDecodeError, TypeError):
            pass
    return cache


def salvar_analise_cv(conn: sqlite3.Connection, cv_hash: str, link: str,
                      porcentagem: int, justificativa: str,
                      habilidades_encontradas: list[str],
                      habilidades_faltantes: list[str]) -> None:
    """Salva o resultado da análise de compatibilidade currículo × vaga. NÃO faz commit."""
    conn.execute(
        """INSERT OR REPLACE INTO analises_cv
           (cv_hash, link, porcentagem, justificativa, habilidades_encontradas, habilidades_faltantes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (cv_hash, link, porcentagem, justificativa,
         json.dumps(habilidades_encontradas, ensure_ascii=False),
         json.dumps(habilidades_faltantes, ensure_ascii=False)),
    )


# ==========================================
# CURRÍCULOS SALVOS
# ==========================================
def salvar_curriculo(conn: sqlite3.Connection, cv_hash: str, nome_arquivo: str,
                     data_upload: str, texto: str) -> None:
    """Salva um currículo extraído para uso futuro. Faz commit (ação unitária do usuário)."""
    conn.execute(
        "INSERT OR IGNORE INTO curriculos_salvos (cv_hash, nome_arquivo, data_upload, texto_extraido) VALUES (?, ?, ?, ?)",
        (cv_hash, nome_arquivo, data_upload, texto),
    )
    conn.commit()


def buscar_curriculos(conn: sqlite3.Connection) -> list[tuple]:
    """Retorna todos os currículos salvos, ordenados por data (mais recente primeiro)."""
    c = conn.cursor()
    try:
        c.execute(
            "SELECT cv_hash, nome_arquivo, data_upload, texto_extraido FROM curriculos_salvos ORDER BY data_upload DESC"
        )
        return c.fetchall()
    except sqlite3.OperationalError:
        return []


# ==========================================
# EDITAL (TEXTO DO PDF)
# ==========================================
def buscar_texto_edital(conn: sqlite3.Connection, link: str) -> str | None:
    """Busca o texto do edital já extraído do cache."""
    c = conn.cursor()
    try:
        c.execute("SELECT texto_edital FROM vagas WHERE link = ?", (link,))
        resultado = c.fetchone()
        if resultado and resultado[0]:
            return resultado[0]
    except sqlite3.OperationalError:
        pass
    return None


def salvar_texto_edital(conn: sqlite3.Connection, link: str, texto: str) -> None:
    """Salva o texto extraído do edital PDF no banco. NÃO faz commit."""
    try:
        conn.execute("UPDATE vagas SET texto_edital = ? WHERE link = ?", (texto, link))
    except sqlite3.OperationalError:
        pass


# ==========================================
# INSCRIÇÃO
# ==========================================
def atualizar_inscricao(conn: sqlite3.Connection, link: str, inscrito: int) -> None:
    """Atualiza o status de inscrição de uma vaga. Faz commit (ação unitária do usuário)."""
    conn.execute("UPDATE vagas SET inscrito = ? WHERE link = ?", (inscrito, link))
    conn.commit()


# ==========================================
# LIMPEZA
# ==========================================
def limpar_cache_ia(conn: sqlite3.Connection) -> None:
    """Remove todas as análises da IA (filtro + currículo). Faz commit (ação destrutiva)."""
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS analises_filtro")
    c.execute("DROP TABLE IF EXISTS analises_cv")
    conn.commit()
    # Recria as tabelas vazias
    migrate(conn)


def buscar_todas_vagas(conn: sqlite3.Connection) -> list[dict]:
    """Retorna todas as vagas para exibição no banco de dados, como lista de dicts."""
    c = conn.cursor()
    c.execute(
        """SELECT inscrito, orgao, cargo, descricao_resumida, status, link,
                  data_encerramento, salario, formacao, regiao, uf,
                  dias_restantes, datas_texto
           FROM vagas"""
    )
    return [
        {
            "inscrito": bool(r[0]),
            "orgao": r[1] or "",
            "cargo": r[2] or "",
            "descricao_resumida": r[3] or "",
            "status": r[4] or "",
            "link": r[5] or "",
            "data_encerramento": r[6] or "Não informada",
            "salario": r[7] or "",
            "formacao": r[8] or "",
            "regiao": r[9] or "",
            "uf": r[10] or "",
            "dias_restantes": r[11] if isinstance(r[11], int) else 0,
            "datas_texto": r[12] or "",
        }
        for r in c.fetchall()
    ]
