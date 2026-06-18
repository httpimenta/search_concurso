"""Testes para src/db.py — migrações, CRUD e cache."""
import os
import pytest
from src import db


@pytest.fixture
def test_db(tmp_path):
    """Cria um banco de dados temporário para cada teste."""
    db_path = str(tmp_path / "test_concursos.db")
    conn = db.get_connection(db_path)
    db.migrate(conn)
    yield conn, db_path
    conn.close()


class TestMigrations:
    """Testes para o sistema de migrações."""

    def test_migrate_cria_tabelas(self, test_db):
        conn, _ = test_db
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas = {row[0] for row in c.fetchall()}
        assert "vagas" in tabelas
        assert "analises_filtro" in tabelas
        assert "analises_cv" in tabelas
        assert "curriculos_salvos" in tabelas
        assert "schema_version" in tabelas

    def test_migrate_idempotente(self, test_db):
        """Rodar migrate duas vezes não deve dar erro."""
        conn, _ = test_db
        db.migrate(conn)  # Segunda vez
        db.migrate(conn)  # Terceira vez
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM schema_version")
        assert c.fetchone()[0] > 0

    def test_wal_mode_ativado(self, test_db):
        conn, _ = test_db
        c = conn.cursor()
        c.execute("PRAGMA journal_mode")
        modo = c.fetchone()[0]
        assert modo == "wal"


class TestVagas:
    """Testes para CRUD de vagas."""

    def test_salvar_e_buscar_vaga(self, test_db):
        conn, _ = test_db
        inseriu = db.salvar_vaga(
            conn, "https://exemplo.com/vaga1", "Prefeitura X", "Analista",
            "Descrição", "aberto", "2026-12-31", "R$ 5.000", "Superior",
            "SUDESTE", "SP", 30, ""
        )
        conn.commit()
        assert inseriu is True

        vagas = db.buscar_vagas_abertas(conn)
        assert len(vagas) == 1
        assert vagas[0]["orgao"] == "Prefeitura X"
        assert vagas[0]["link"] == "https://exemplo.com/vaga1"

    def test_salvar_vaga_duplicada(self, test_db):
        conn, _ = test_db
        db.salvar_vaga(conn, "https://exemplo.com/vaga1", "Org", "Cargo",
                       "Desc", "aberto", "", "", "", "", "", 0, "")
        conn.commit()
        inseriu = db.salvar_vaga(conn, "https://exemplo.com/vaga1", "Org2", "Cargo2",
                                  "Desc2", "aberto", "", "", "", "", "", 0, "")
        assert inseriu is False

    def test_buscar_links_salvos(self, test_db):
        conn, _ = test_db
        db.salvar_vaga(conn, "https://a.com", "A", "C", "D", "aberto", "", "", "", "", "", 0, "")
        db.salvar_vaga(conn, "https://b.com", "B", "C", "D", "aberto", "", "", "", "", "", 0, "")
        conn.commit()
        links = db.buscar_links_salvos(conn)
        assert links == {"https://a.com", "https://b.com"}

    def test_atualizar_status(self, test_db):
        conn, _ = test_db
        db.salvar_vaga(conn, "https://a.com", "A", "C", "D", "aberto", "", "", "", "", "", 0, "")
        db.salvar_vaga(conn, "https://b.com", "B", "C", "D", "aberto", "", "", "", "", "", 0, "")
        conn.commit()

        db.atualizar_status_vagas(conn, ["https://a.com"], ["https://b.com"])

        vagas = db.buscar_vagas_abertas(conn)
        assert len(vagas) == 1
        assert vagas[0]["link"] == "https://a.com"


class TestCacheFiltro:
    """Testes para o cache de filtro de profissão."""

    def test_salvar_e_buscar_filtro(self, test_db):
        conn, _ = test_db
        db.salvar_analise_filtro(conn, "https://a.com", "UX Designer", 1)
        db.salvar_analise_filtro(conn, "https://a.com", "Dev Backend", 0)
        conn.commit()

        cache = db.buscar_cache_filtro(conn, ["UX Designer", "Dev Backend"])
        assert cache["https://a.com"]["UX Designer"] is True
        assert cache["https://a.com"]["Dev Backend"] is False

    def test_batch_insert(self, test_db):
        conn, _ = test_db
        analises = [
            ("https://a.com", "UX", 1),
            ("https://b.com", "UX", 0),
            ("https://c.com", "Dev", 1),
        ]
        db.salvar_analises_filtro_batch(conn, analises)

        cache = db.buscar_cache_filtro(conn, ["UX", "Dev"])
        assert cache["https://a.com"]["UX"] is True
        assert cache["https://b.com"]["UX"] is False
        assert cache["https://c.com"]["Dev"] is True

    def test_buscar_profissoes_salvas(self, test_db):
        conn, _ = test_db
        db.salvar_analise_filtro(conn, "https://a.com", "UX Designer", 1)
        db.salvar_analise_filtro(conn, "https://b.com", "Product Designer", 0)
        conn.commit()

        profs = db.buscar_profissoes_salvas(conn)
        assert "Product Designer" in profs
        assert "UX Designer" in profs


class TestCacheCV:
    """Testes para o cache de análise de currículo."""

    def test_salvar_e_buscar_cv(self, test_db):
        conn, _ = test_db
        db.salvar_analise_cv(
            conn, "abc123", "https://a.com", 85,
            "Boa compatibilidade", ["Python", "SQL"], ["Docker"]
        )
        conn.commit()

        cache = db.buscar_cache_cv(conn, "abc123", ["https://a.com"])
        assert "https://a.com" in cache
        assert cache["https://a.com"]["porcentagem"] == 85
        assert "Python" in cache["https://a.com"]["habilidades_encontradas"]
        assert "Docker" in cache["https://a.com"]["habilidades_faltantes"]


class TestCurriculos:
    """Testes para currículos salvos."""

    def test_salvar_e_buscar_curriculo(self, test_db):
        conn, _ = test_db
        db.salvar_curriculo(conn, "hash1", "cv.pdf", "01/01/2026", "texto do cv")

        cvs = db.buscar_curriculos(conn)
        assert len(cvs) == 1
        assert cvs[0][1] == "cv.pdf"
        assert cvs[0][3] == "texto do cv"
