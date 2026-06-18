"""
Modelos de dados tipados do Caçador de Concursos IA.
Baseados na estrutura real da API MCP do PCI Concursos.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Datas:
    """Datas de inscrição de um concurso."""
    inicio: str = ""
    fim: str = ""
    texto: str = ""           # Ex: "Prorrogado", "Reaberto"
    aberto: bool = True
    dias_restantes: int = 0

    @classmethod
    def from_dict(cls, d: dict | None) -> Datas:
        if not d:
            return cls()
        return cls(
            inicio=d.get("inicio", ""),
            fim=d.get("fim", ""),
            texto=d.get("texto", ""),
            aberto=d.get("aberto", True),
            dias_restantes=d.get("dias_restantes", 0),
        )


@dataclass
class Noticia:
    """Notícia/link oficial do concurso."""
    id: int = 0
    titulo: str = ""
    link: str = ""
    imagem: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> Noticia:
        if not d:
            return cls()
        return cls(
            id=d.get("id", 0),
            titulo=d.get("titulo", ""),
            link=d.get("link", ""),
            imagem=d.get("imagem", ""),
        )


@dataclass
class Vaga:
    """Representa um concurso público com todos os seus dados."""
    id: int = 0
    titulo: str = ""              # Nome do órgão
    cargos_resumo: str = ""
    cargos: list[str] = field(default_factory=list)
    vagas_salario: str = ""
    formacao: str = ""
    regiao: str = ""
    uf: str = ""
    datas: Datas = field(default_factory=Datas)
    noticia: Noticia = field(default_factory=Noticia)

    # Campos internos (preenchidos localmente, não vêm da API)
    texto_completo: bool = False
    descricao_resumida: str = ""
    texto_edital: str | None = None

    @property
    def link(self) -> str:
        """Atalho para o link principal da vaga (noticia.link)."""
        return self.noticia.link

    @property
    def orgao(self) -> str:
        """Alias para manter compatibilidade — o órgão é o 'titulo' da API."""
        return self.titulo

    @property
    def cargo(self) -> str:
        """Retorna os cargos como string separada por vírgula."""
        if self.cargos:
            return ", ".join(self.cargos)
        return self.cargos_resumo or "Diversos (Ver edital)"

    @classmethod
    def from_api_dict(cls, d: dict) -> Vaga:
        """Constrói uma Vaga a partir do dicionário retornado pela API MCP."""
        return cls(
            id=d.get("id", 0),
            titulo=d.get("titulo", "Órgão Desconhecido"),
            cargos_resumo=d.get("cargos_resumo", ""),
            cargos=d.get("cargos", []),
            vagas_salario=d.get("vagas_salario", ""),
            formacao=d.get("formacao", ""),
            regiao=d.get("regiao", ""),
            uf=d.get("uf", ""),
            datas=Datas.from_dict(d.get("datas")),
            noticia=Noticia.from_dict(d.get("noticia")),
            descricao_resumida=d.get("descricao", "Detalhes disponíveis no edital."),
        )

    @classmethod
    def from_db_row(cls, row: tuple) -> Vaga:
        """Constrói uma Vaga a partir de uma linha do banco de dados."""
        return cls(
            titulo=row[0] if row[0] else "",
            cargos_resumo=row[1] if row[1] else "",
            descricao_resumida=row[2] if row[2] else "",
            noticia=Noticia(link=row[3] if row[3] else ""),
            vagas_salario=row[4] if row[4] else "",
            formacao=row[5] if row[5] else "",
            regiao=row[6] if row[6] else "",
            uf=row[7] if row[7] else "",
        )


@dataclass
class AnaliseCV:
    """Resultado da análise de compatibilidade currículo × vaga."""
    porcentagem: int = 0
    justificativa: str = "Sem justificativa."
    habilidades_encontradas: list[str] = field(default_factory=list)
    habilidades_faltantes: list[str] = field(default_factory=list)
