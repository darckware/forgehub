"""add marketing, social, content, and interpersonal prompt techniques

Revision ID: a41c8e7d2f90
Revises: dd853ac4226c
Create Date: 2026-08-14 18:31:00
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a41c8e7d2f90"
down_revision: Union[str, Sequence[str], None] = "dd853ac4226c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROWS = [
    ("marketing_strategy", "marketing", "Estratégia de marketing", "Define mercado, público, posicionamento, objetivos, canais, orçamento e métricas.", "Planejar marketing de uma marca, produto ou serviço antes de produzir peças isoladas.", "Quando a necessidade é somente revisar uma peça com estratégia já aprovada.", ["estratégia de marketing", "plano de marketing", "marketing digital", "público e canais"], "Defina contexto, público, posicionamento, objetivos mensuráveis, jornada, canais, mensagem, recursos, calendário, métricas e riscos; não invente dados de mercado.", "high", "primary"),
    ("campaign_planning", "marketing", "Planejamento de campanha", "Conecta objetivo, audiência, oferta, conceito, canais, peças, cronograma e medição.", "Campanhas institucionais, promocionais, sazonais ou de aquisição.", "Quando não existe objetivo ou oferta minimamente definidos.", ["campanha de marketing", "campanha promocional", "campanha publicitária", "campanha sazonal"], "Estruture objetivo, segmento, insight, proposta, conceito criativo, canais, peças, sequência, cronograma, orçamento, métricas e critérios de otimização.", "high", "primary"),
    ("content_marketing", "marketing", "Marketing de conteúdo", "Planeja conteúdo útil por jornada, intenção, formato, distribuição e conversão.", "Atrair, educar e nutrir audiência com conteúdo recorrente.", "Quando a comunicação é uma oferta direta sem necessidade editorial.", ["marketing de conteúdo", "conteúdo para atrair", "estratégia editorial", "funil de conteúdo"], "Mapeie público, dores, estágio da jornada, pilares, formatos, distribuição, frequência, conversão e métricas, mantendo utilidade antes da promoção.", "high", "primary"),
    ("seo_content", "marketing", "Conteúdo orientado a SEO", "Alinha intenção de busca, tópicos, estrutura, evidência e conversão sem sacrificar leitura.", "Artigos, páginas e guias destinados à descoberta orgânica.", "Quando não existe pesquisa de intenção ou o canal não depende de busca.", ["seo", "palavra-chave", "busca orgânica", "conteúdo para google"], "Defina intenção de busca, tópico principal, entidades relacionadas, estrutura, resposta direta, evidências, links e conversão; evite repetição artificial de palavras-chave.", "high", "primary"),
    ("email_marketing", "marketing", "E-mail marketing", "Estrutura assunto, preheader, mensagem, segmentação, CTA e sequência.", "Newsletters, nutrição, onboarding, recuperação e campanhas por e-mail.", "Mensagens transacionais obrigatórias ou sem consentimento adequado.", ["email marketing", "newsletter", "sequência de emails", "nutrição de leads"], "Defina segmento, etapa da jornada, objetivo único, assunto e preheader honestos, corpo escaneável, CTA, sequência, personalização e métricas; respeite consentimento e descadastro.", "medium", "primary"),
    ("product_launch", "marketing", "Lançamento de produto", "Coordena narrativa, público, canais e fases antes, durante e depois do lançamento.", "Lançar produto, funcionalidade, serviço ou nova versão.", "Quando o produto ainda não possui proposta, disponibilidade ou critérios de sucesso.", ["lançamento de produto", "lançar produto", "go to market", "campanha de lançamento"], "Estruture público, problema, proposta, diferenciais verificáveis, fases de aquecimento/lançamento/sustentação, canais, ativos, responsabilidades, métricas e contingências.", "very_high", "primary"),
    ("conversion_funnel", "marketing", "Funil e conversão", "Modela etapas, objeções, mensagens, eventos e experimentos ao longo da conversão.", "Aquisição, ativação, vendas, retenção e recuperação de abandono.", "Quando sucesso não pode ser reduzido a uma conversão ou exige análise qualitativa ampla.", ["funil de vendas", "conversão", "gerar leads", "jornada de compra", "cro"], "Defina evento final e microconversões, segmentos, entradas, fricções, objeções, mensagens, evidências, instrumentação e hipóteses de teste sem prometer resultados.", "high", "primary"),
    ("social_media_strategy", "social_media", "Estratégia de redes sociais", "Define papel de cada plataforma, público, pilares, formatos, cadência e métricas.", "Planejar presença recorrente de marca ou produto em redes sociais.", "Quando o pedido é uma publicação isolada e a estratégia já existe.", ["estratégia de redes sociais", "plano para redes sociais", "social media", "presença nas redes"], "Defina objetivo, audiência, plataformas e papel de cada uma, pilares, formatos, voz, cadência, distribuição, comunidade, governança e métricas.", "high", "primary"),
    ("social_media_post", "social_media", "Post para rede social", "Cria gancho, corpo, CTA, legenda e elementos adequados à plataforma.", "Posts para Instagram, LinkedIn, TikTok, X, Facebook ou outra plataforma definida.", "Quando plataforma, público e objetivo não são conhecidos nem inferíveis.", ["post para instagram", "post para linkedin", "legenda", "hashtags", "post para rede social"], "Adapte o texto à plataforma, público e formato; crie gancho honesto, valor central, CTA proporcional, legenda escaneável e hashtags somente quando úteis.", "medium", "primary"),
    ("social_content_calendar", "social_media", "Calendário editorial social", "Distribui pilares, formatos, campanhas e cadência em um calendário executável.", "Organizar semanas ou meses de publicação em uma ou várias redes.", "Quando ainda não existem objetivo, capacidade de produção ou pilares editoriais.", ["calendário editorial", "calendário de posts", "planejamento mensal instagram", "cronograma de redes sociais"], "Monte calendário por data, plataforma, objetivo, pilar, formato, ideia, CTA, responsável e status; equilibre valor, relacionamento e promoção conforme capacidade real.", "high", "primary"),
    ("paid_social_ads", "social_media", "Anúncios em redes sociais", "Estrutura audiência, hipótese, criativo, copy, oferta, variações e medição.", "Campanhas pagas em Meta, LinkedIn, TikTok ou plataformas sociais.", "Quando não há oferta, página de destino, orçamento ou rastreamento mínimo.", ["facebook ads", "instagram ads", "meta ads", "anúncio pago", "tráfego pago"], "Defina objetivo, audiência, exclusões, hipótese, oferta, criativo, copy, CTA, destino, variações, orçamento, eventos e critérios de pausa/otimização; não prometa performance.", "high", "primary"),
    ("community_engagement", "social_media", "Engajamento e comunidade", "Planeja conversas, moderação, respostas e vínculos contínuos com a audiência.", "Comunidades, comentários, atendimento social e fortalecimento de relacionamento.", "Quando a interação pretendida manipula, assedia ou simula apoio inexistente.", ["engajamento nas redes", "gestão de comunidade", "responder comentários", "comunidade online"], "Defina tom, tipos de interação, perguntas, tempo de resposta, moderação, escalonamento, tratamento de críticas e sinais de saúde da comunidade.", "medium", "primary"),
    ("influencer_marketing", "social_media", "Marketing de influência", "Estrutura seleção, briefing, autenticidade, entregas, direitos e medição.", "Parcerias com criadores, embaixadores e conteúdo patrocinado.", "Quando não há alinhamento de público, transparência publicitária ou condições de uso definidas.", ["marketing de influência", "influenciador", "criadores de conteúdo", "publipost"], "Defina objetivo, perfil de criador, critérios de aderência, briefing com liberdade autêntica, entregas, divulgação publicitária, direitos de uso, riscos e métricas.", "high", "primary"),
    ("social_media_analytics", "social_media", "Análise de redes sociais", "Transforma métricas de alcance, retenção, engajamento e conversão em hipóteses acionáveis.", "Avaliar desempenho de conteúdo, campanhas e canais sociais.", "Quando faltam período, objetivo ou dados comparáveis.", ["métricas de redes sociais", "analisar instagram", "relatório social media", "engajamento e alcance"], "Relacione métricas ao objetivo e ao período, normalize comparações, separe sinal de vaidade, identifique padrões e proponha hipóteses e próximos testes sem confundir correlação com causa.", "high", "primary"),
    ("content_brief", "content", "Briefing de conteúdo", "Consolida objetivo, público, mensagem, fontes, formato, canal, voz e critérios antes da redação.", "Conteúdo novo com várias restrições ou pessoas envolvidas na aprovação.", "Quando o texto é simples e todas as decisões já estão explícitas.", ["briefing de conteúdo", "brief editorial", "planejar conteúdo", "contexto do conteúdo"], "Organize objetivo, público, conhecimento prévio, mensagem central, fontes, canal, formato, voz, extensão, CTA, restrições e critérios de aprovação; marque lacunas sem inventar decisões.", "medium", "primary"),
    ("brand_voice_content", "content", "Conteúdo com voz de marca", "Preserva personalidade, tom, vocabulário e limites editoriais da marca.", "Produzir conteúdo consistente com identidade e exemplos de comunicação existentes.", "Quando não há diretrizes nem amostras confiáveis de voz.", ["voz da marca", "tom de voz", "conteúdo da marca", "manual de voz"], "Extraia princípios de voz das diretrizes ou exemplos fornecidos, preserve fatos e mensagem, e aplique tom, ritmo, vocabulário e limites de forma consistente sem caricaturar a marca.", "medium", "both"),
    ("source_grounded_content", "content", "Conteúdo fundamentado em fontes", "Cria conteúdo factual distinguindo fonte, inferência, opinião e incerteza.", "Artigos, roteiros e posts que dependem de dados, estudos ou acontecimentos verificáveis.", "Ficção ou conteúdo assumidamente opinativo sem alegações factuais externas.", ["conteúdo com fontes", "artigo com referências", "conteúdo factual", "dados verificados"], "Use apenas fontes disponíveis ou autorizadas, associe alegações às evidências, preserve datas e escopo, sinalize inferências e nunca fabrique números, citações ou referências.", "high", "primary"),
    ("assertive_communication", "soft_skills", "Comunicação assertiva", "Expressa objetivo, contexto, limites e pedidos com clareza e respeito.", "Alinhar expectativas, fazer solicitações ou posicionar-se sem agressividade nem passividade.", "Quando a situação exige apenas uma instrução técnica neutra.", ["comunicação assertiva", "falar com clareza", "alinhar expectativas", "colocar limites"], "Formule a mensagem com fatos observáveis, impacto, necessidade, pedido específico e abertura ao diálogo; preserve respeito e evite acusações, generalizações ou manipulação.", "medium", "primary"),
    ("active_listening", "soft_skills", "Escuta ativa", "Ajuda a compreender perspectiva, necessidade, emoção e pontos ainda ambíguos.", "Conversas de descoberta, apoio, liderança, atendimento e resolução de problemas humanos.", "Quando a pessoa pediu objetivamente uma ação urgente e já forneceu contexto suficiente.", ["escuta ativa", "entender a pessoa", "ouvir melhor", "compreender a equipe"], "Priorize compreender antes de responder: reconheça o que foi dito, diferencie fatos de interpretações, faça perguntas abertas e confirme o entendimento sem presumir sentimentos ou intenções.", "medium", "primary"),
    ("empathetic_response", "soft_skills", "Resposta empática", "Reconhece a experiência da pessoa sem inventar sentimentos nem abandonar o objetivo da conversa.", "Mensagens sensíveis, frustração, mudança, suporte ou comunicação de impacto.", "Quando empatia performática desviaria de uma emergência ou decisão objetiva.", ["responder com empatia", "mensagem empática", "pessoa frustrada", "acolher"], "Reconheça concretamente a perspectiva e o impacto descritos, use linguagem humana e respeitosa, evite clichês e avance para ajuda ou próximo passo compatível com o que a pessoa pediu.", "medium", "both"),
    ("constructive_feedback", "soft_skills", "Feedback construtivo", "Transforma observações em feedback específico, acionável e orientado ao desenvolvimento.", "Dar feedback sobre comportamento, trabalho, colaboração ou desempenho.", "Quando não há observação concreta ou autoridade legítima para avaliar.", ["dar feedback", "feedback construtivo", "avaliação de desempenho", "conversa de feedback"], "Separe pessoa de comportamento, descreva situação e evidência, explique impacto, reconheça pontos fortes, proponha mudança observável e combine acompanhamento; não diagnostique caráter ou intenção.", "high", "primary"),
    ("conflict_resolution", "soft_skills", "Resolução de conflitos", "Mapeia interesses, fatos, percepções e opções para construir um acordo praticável.", "Divergências entre pessoas, equipes, clientes ou parceiros.", "Quando há abuso, ameaça ou risco que exige proteção e escalonamento, não mediação informal.", ["resolver conflito", "conflito na equipe", "desentendimento", "mediar conflito"], "Defina partes e segurança, separe posições de interesses, estabeleça fatos compartilhados, dê espaço equivalente, formule opções e registre acordo, responsáveis, limites e revisão.", "high", "primary"),
    ("difficult_conversation", "soft_skills", "Conversa difícil", "Prepara uma conversa sensível com objetivo, fatos, limites, escuta e próximos passos.", "Desempenho, negativas, mudança de papel, cobranças, limites ou notícias difíceis.", "Quando a conversa deve ser conduzida por RH, jurídico ou suporte especializado.", ["conversa difícil", "como dizer não", "conversa delicada", "comunicar problema"], "Prepare objetivo e fatos verificáveis, escolha abertura direta e respeitosa, antecipe reações sem roteirizar a pessoa, formule perguntas, limites, opções e próximos passos; não esconda a mensagem central.", "high", "primary"),
    ("negotiation", "soft_skills", "Negociação colaborativa", "Organiza interesses, alternativas, concessões, critérios e acordos sustentáveis.", "Negociar prazo, escopo, recursos, responsabilidades, preço ou prioridades.", "Quando consentimento é impossível, existe coerção ou a decisão não é negociável.", ["negociar", "negociação", "chegar a um acordo", "negociar prazo"], "Defina interesses, restrições, alternativas e critérios objetivos de ambos os lados; proponha trocas explícitas, evite pressão enganosa e registre condições, responsabilidades e pontos de revisão.", "high", "primary"),
    ("collaborative_leadership", "soft_skills", "Liderança colaborativa", "Alinha direção, autonomia, responsabilidades, segurança psicológica e prestação de contas.", "Liderar equipes, mudanças, decisões coletivas ou iniciativas multidisciplinares.", "Quando a decisão urgente e regulada exige comando claro sem deliberação ampla.", ["liderança", "liderar equipe", "liderança colaborativa", "motivar equipe"], "Comunique propósito e limites, envolva as pessoas nas decisões apropriadas, distribua autoridade e responsabilidade, torne critérios visíveis, remova impedimentos e acompanhe compromissos sem microgerenciar.", "high", "primary"),
    ("team_collaboration", "soft_skills", "Colaboração em equipe", "Melhora acordos de trabalho, coordenação, confiança e resolução de dependências.", "Times com múltiplas funções, handoffs, retrabalho ou comunicação fragmentada.", "Quando o problema é falta de capacidade ou recurso, não de colaboração.", ["colaboração em equipe", "trabalho em equipe", "melhorar colaboração", "integração da equipe"], "Defina objetivo comum, papéis, interfaces, decisões, canais, cadência, critérios de pronto e formas de levantar riscos; trate divergência como informação e torne dependências explícitas.", "medium", "primary"),
    ("coaching_conversation", "soft_skills", "Conversa de coaching", "Usa perguntas e reflexão para apoiar autonomia, aprendizagem e plano de ação.", "Desenvolvimento profissional, tomada de decisão e desbloqueio de alguém capaz de agir.", "Quando a pessoa precisa de instrução direta, cuidado clínico ou decisão que não lhe pertence.", ["coaching", "desenvolver pessoa", "mentoria", "plano de desenvolvimento"], "Ajude a pessoa a definir objetivo, realidade, opções e compromisso por meio de perguntas abertas; ofereça sugestões com permissão, preserve autonomia e termine com ação, prazo e forma de acompanhamento.", "high", "primary"),
    ("skill_creation", "agent_skills", "Criação de skill de agente", "Define gatilhos, entradas, workflow, ferramentas, limites, saídas e validação de uma capacidade reutilizável.", "Criar uma skill para Codex, agentes ou outro runtime extensível.", "Quando a tarefa é uma execução única que não será reutilizada.", ["criar skill", "nova skill", "skill para agente", "skill do codex"], "Defina objetivo estreito, gatilhos positivos e negativos, entradas, pré-condições, workflow, ferramentas, recursos, limites de autoridade, erros, saídas e testes; siga o formato canônico do runtime alvo.", "high", "primary"),
    ("skill_update", "agent_skills", "Atualização de skill de agente", "Evolui uma skill existente preservando contratos e corrigindo lacunas observadas.", "Modificar comportamento, instruções, scripts ou recursos de uma skill instalada.", "Quando a skill original e seus consumidores não estão disponíveis para inspeção.", ["atualizar skill", "melhorar skill", "corrigir skill", "editar skill"], "Inspecione integralmente a skill e seus recursos, identifique contratos e casos existentes, altere somente o necessário, preserve compatibilidade ou documente a migração e revalide os gatilhos.", "high", "primary"),
    ("skill_evaluation", "agent_skills", "Avaliação de skill de agente", "Testa descoberta, seleção, execução, limites e qualidade das saídas com casos positivos e negativos.", "Validar uma skill antes de instalar, publicar ou ampliar seu uso.", "Quando ainda não existe comportamento ou critério de sucesso definido.", ["testar skill", "avaliar skill", "validação de skill", "casos de teste skill"], "Crie matriz de casos que devem e não devem acionar a skill, entradas normais e adversas, resultados esperados, limites de segurança e regressões; avalie evidências reais, não apenas o texto das instruções.", "high", "primary"),
    ("skill_documentation", "agent_skills", "Documentação de skill de agente", "Explica finalidade, gatilhos, requisitos, uso, exemplos, limites e solução de problemas.", "Preparar uma skill para descoberta e uso correto por pessoas e agentes.", "Como substituto de instruções executáveis ou testes da própria skill.", ["documentar skill", "manual da skill", "exemplo de skill", "como usar skill"], "Documente finalidade, quando usar e evitar, requisitos, entradas, fluxo, saídas, exemplos mínimos, limites, falhas conhecidas, troubleshooting e versionamento sem duplicar detalhes internos desnecessários.", "medium", "primary"),
]


def upgrade() -> None:
    op.drop_constraint("ck_prompt_techniques_category", "prompt_techniques", schema="company", type_="check")
    op.create_check_constraint(
        "ck_prompt_techniques_category",
        "prompt_techniques",
        "category IN ('text','structure','reasoning','software','agentic','research','content','marketing','social_media','soft_skills','agent_skills','design','automation','image','video')",
        schema="company",
    )
    techniques = sa.table(
        "prompt_techniques",
        sa.column("id", sa.UUID()), sa.column("code", sa.String()),
        sa.column("category", sa.String()), sa.column("name", sa.String()),
        sa.column("summary", sa.Text()), sa.column("when_to_use", sa.Text()),
        sa.column("when_to_avoid", sa.Text()), sa.column("requirements", postgresql.JSONB()),
        sa.column("compatible_with", postgresql.JSONB()), sa.column("conflicts_with", postgresql.JSONB()),
        sa.column("match_terms", postgresql.JSONB()), sa.column("instruction_template", sa.Text()),
        sa.column("effort", sa.String()), sa.column("selection_mode", sa.String()),
        sa.column("template_version", sa.Integer()), sa.column("sort_order", sa.Integer()),
        sa.column("is_builtin", sa.Boolean()), sa.column("is_active", sa.Boolean()), schema="company",
    )
    counters = {
        "content": 0,
        "marketing": 0,
        "social_media": 0,
        "soft_skills": 0,
        "agent_skills": 0,
    }
    seed_rows = []
    for code, category, name, summary, when, avoid, terms, template, effort, mode in _ROWS:
        counters[category] += 1
        seed_rows.append({
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"forgehub:prompt-technique:{code}"),
            "code": code, "category": category, "name": name, "summary": summary,
            "when_to_use": when, "when_to_avoid": avoid, "requirements": [],
            "compatible_with": [], "conflicts_with": [], "match_terms": terms,
            "instruction_template": template, "effort": effort, "selection_mode": mode,
            "template_version": 1,
            "sort_order": {
                "content": 610,
                "marketing": 1200,
                "social_media": 1300,
                "soft_skills": 1400,
                "agent_skills": 1500,
            }[category] + counters[category],
            "is_builtin": True, "is_active": True,
        })
    op.bulk_insert(techniques, seed_rows)


def downgrade() -> None:
    codes = [row[0] for row in _ROWS]
    op.execute(
        sa.text("DELETE FROM company.prompt_techniques WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=codes, type_=postgresql.ARRAY(sa.String()))
        )
    )
    op.drop_constraint("ck_prompt_techniques_category", "prompt_techniques", schema="company", type_="check")
    op.create_check_constraint(
        "ck_prompt_techniques_category", "prompt_techniques",
        "category IN ('text','structure','reasoning','software','agentic','research','content','design','automation','image','video')",
        schema="company",
    )
