"""
Prompts centralizados para todas as chamadas à IA Gemini.
Evita duplicação entre app_v2.py e busca_diaria.py.
"""

PROMPT_PENTE_FINO = """
O candidato atua nas áreas: {profissoes}.
Avalie se os seguintes cargos de concurso têm ALGUMA chance (mesmo que mínima)
de englobar as áreas do candidato.

DIRETRIZES:
1. APROVE CARGOS GENÉRICOS: Nomes como "Analista de Tecnologia", "Analista de Sistemas",
   "Técnico de Nível Superior", "Especialista" podem esconder vagas relevantes. Na dúvida, retorne true.
2. REJEITE ESPECIALIDADES DISTINTAS: Não confunda as áreas. Se o candidato é de UX/UI/Product Design,
   NÃO aprove vagas estritamente focadas em "Design Gráfico", "Web Design Clássico", "Publicidade".
3. SENIORIDADE: Quando uma área vier com a senioridade entre parênteses (ex: "UX Designer (Sênior)"),
   trate-a apenas como uma pista de nível, NÃO como motivo de rejeição nesta etapa — o nome do cargo
   raramente revela a senioridade. Na dúvida sobre o nível, retorne true (o filtro detalhado decide depois).

Retorne EXATAMENTE neste formato JSON:
[ {{"id": 0, "relevante": true}}, {{"id": 1, "relevante": false}} ]

Cargos:
{cargos}
"""

PROMPT_FILTRO = """
Você é um recrutador especialista. O candidato atua nas seguintes áreas: {profissoes}.
Muitas vezes o nome oficial do cargo não reflete a profissão exata,
mas as atividades descritas no edital são exatamente o que o candidato faz.

Determine se cada vaga é compatível com ALGUMA das áreas do candidato.
Se for compatível, liste quais áreas exatas dão match.

SENIORIDADE: Quando uma área vier com a senioridade entre parênteses
(ex: "UX Designer (Sênior)"), considere também se o nível exigido pela vaga é compatível,
inferindo-o pelos requisitos do edital (anos de experiência, escolaridade, atribuições):
- Júnior: pouca/nenhuma experiência exigida, perfil de entrada.
- Pleno: experiência intermediária.
- Sênior: experiência sólida, liderança técnica, requisitos mais altos.
- Estágio/Trainee: vaga de estágio, trainee ou aprendiz.
Só dê match dessa área quando a senioridade também for compatível. Áreas SEM senioridade
entre parênteses devem ser avaliadas apenas pela compatibilidade da área, ignorando o nível.
Ao listar em "profissoes_match", repita a área exatamente como recebida (com o nível, se houver).

Retorne no formato JSON:
[ {{"id": 0, "compativel": true, "profissoes_match": ["Service Designer"]}},
  {{"id": 1, "compativel": false, "profissoes_match": []}} ]

Vagas:
{vagas}
"""

PROMPT_CV = """{vagas_texto}
Para cada vaga, dê uma nota de 0 a 100 representando a compatibilidade real
entre as experiências do currículo e os requisitos exigidos.

Retorne no formato JSON:
[
    {{
        "id": 0,
        "porcentagem": 85,
        "justificativa": "breve explicação...",
        "habilidades_encontradas": ["habilidade 1"],
        "habilidades_faltantes": ["habilidade 2"]
    }}
]
"""
