"""add classified prompt techniques catalog

Revision ID: 649a49c930d1
Revises: d4a8f21c6b7e
Create Date: 2026-08-14 17:17:02.734202

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "649a49c930d1"
down_revision: Union[str, Sequence[str], None] = "d4a8f21c6b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    techniques = op.create_table(
        "prompt_techniques",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("when_to_use", sa.Text(), nullable=False),
        sa.Column("when_to_avoid", sa.Text(), nullable=True),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("compatible_with", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("conflicts_with", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("match_terms", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("instruction_template", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("effort", sa.String(length=16), server_default="low", nullable=False),
        sa.Column("selection_mode", sa.String(length=12), server_default="both", nullable=False),
        sa.Column("template_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('text','structure','reasoning','software','agentic','research','content','image','video')",
            name="ck_prompt_techniques_category",
        ),
        sa.CheckConstraint(
            "effort IN ('low','medium','high','very_high')",
            name="ck_prompt_techniques_effort",
        ),
        sa.CheckConstraint(
            "selection_mode IN ('primary','addon','both')",
            name="ck_prompt_techniques_selection_mode",
        ),
        sa.CheckConstraint("template_version > 0", name="ck_prompt_techniques_template_version"),
        sa.CheckConstraint("sort_order >= 0", name="ck_prompt_techniques_sort_order"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        schema="company",
    )
    op.create_index(
        "ix_prompt_techniques_catalog",
        "prompt_techniques",
        ["is_active", "category", "sort_order"],
        schema="company",
    )

    # Broad initial catalog. New techniques are data additions, not schema
    # changes; the stable code is what future saved selections reference.
    rows = [
        ("automatic", "structure", "Automática", "Seleciona a estratégia adequada ao objetivo e à complexidade do rascunho.", "Quando o usuário não sabe qual técnica escolher.", "Quando o processo precisa ser totalmente previsível e auditável.", "Analise o rascunho e aplique somente as técnicas necessárias, explicando pressupostos dentro do próprio prompt final.", "low", "primary"),
        ("grammar_correction", "text", "Correção gramatical", "Corrige ortografia, concordância e pontuação sem alterar a intenção.", "Textos já completos que precisam de revisão linguística.", "Quando a estrutura e os requisitos também precisam ser reconstruídos.", "Corrija somente problemas linguísticos e preserve integralmente significado, identificadores e restrições.", "low", "addon"),
        ("clarity_objectivity", "text", "Clareza e objetividade", "Remove ambiguidades, repetições e linguagem imprecisa.", "Instruções compreensíveis, mas vagas ou excessivamente longas.", "Quando nuances estilísticas deliberadas devem permanecer intactas.", "Torne a solicitação direta, inequívoca e verificável sem inventar requisitos.", "low", "both"),
        ("tone_adaptation", "text", "Adequação de tom", "Adapta voz, formalidade e vocabulário ao público informado.", "Conteúdo destinado a um público ou canal específico.", "Quando o público e o tom desejado não foram informados.", "Ajuste tom e vocabulário ao público indicado, preservando fatos e intenção.", "low", "addon"),
        ("simplify_language", "text", "Simplificação de linguagem", "Reduz jargão e complexidade sem perder precisão.", "Comunicação para iniciantes ou público não técnico.", "Documentos normativos nos quais termos exatos não podem ser substituídos.", "Simplifique a linguagem; preserve termos técnicos indispensáveis e explique-os brevemente.", "low", "addon"),
        ("summarization", "text", "Síntese", "Reduz o texto aos objetivos, restrições e informações essenciais.", "Rascunhos repetitivos ou maiores do que o necessário.", "Quando detalhes fornecidos funcionam como critérios de aceite.", "Comprima o texto sem remover requisitos, exceções, evidências ou critérios verificáveis.", "low", "addon"),
        ("structured_prompt", "structure", "Prompt estruturado", "Organiza objetivo, contexto, requisitos, restrições, entregáveis e critérios de aceite.", "Solicitações complexas ou que serão executadas por agentes.", "Perguntas simples que não justificam uma estrutura extensa.", "Estruture em seções úteis e elimine seções vazias ou artificiais.", "medium", "both"),
        ("role_persona", "structure", "Papel especializado", "Define a competência e a perspectiva necessárias para executar a tarefa.", "Quando uma especialização muda materialmente a resposta.", "Quando a persona seria apenas decorativa ou teatral.", "Defina somente o papel profissional relevante e suas responsabilidades concretas.", "low", "addon"),
        ("few_shot", "structure", "Few-shot por exemplos", "Inclui exemplos de entrada e saída que demonstram padrão, formato ou estilo.", "Classificação, transformação ou formato difícil de descrever apenas com regras.", "Quando não existem exemplos confiáveis; não invente exemplos como se fossem fornecidos.", "Use os exemplos fornecidos como demonstração, separe-os claramente e não os trate como novos dados.", "medium", "addon"),
        ("acceptance_criteria", "structure", "Critérios de aceite", "Converte expectativas em condições observáveis de conclusão.", "Implementações, documentos e entregas que precisam ser verificadas.", "Exploração aberta sem resultado previamente definido.", "Acrescente critérios mensuráveis e coerentes apenas com o objetivo informado.", "low", "addon"),
        ("structured_output", "structure", "Saída estruturada", "Especifica formato final como JSON, tabela, checklist ou seções fixas.", "Respostas consumidas por sistemas ou fluxos padronizados.", "Criação aberta em que uma estrutura rígida reduziria a qualidade.", "Defina exatamente o formato de saída e não misture texto fora dele quando isso quebrar o consumidor.", "low", "addon"),
        ("task_decomposition", "reasoning", "Decomposição da tarefa", "Divide um objetivo complexo em partes menores e verificáveis.", "Trabalho com múltiplos componentes ou dependências.", "Tarefas atômicas que podem ser resolvidas diretamente.", "Divida o trabalho por dependências e resultados verificáveis, mantendo a integração final explícita.", "medium", "both"),
        ("plan_first", "reasoning", "Planejar antes de executar", "Exige inspeção, riscos e plano proporcional antes das alterações.", "Mudanças amplas, sensíveis ou com dependências desconhecidas.", "Correções triviais em que planejar adiciona apenas latência.", "Inspecione o estado real, forme um plano curto e ajuste-o conforme as evidências antes de executar.", "medium", "both"),
        ("hypothesis_analysis", "reasoning", "Análise por hipóteses", "Formula causas possíveis e procura evidências para confirmá-las ou descartá-las.", "Diagnósticos com causa ainda desconhecida.", "Quando a causa já foi comprovada por evidência direta.", "Liste hipóteses plausíveis, priorize-as e teste cada uma com evidência observável.", "medium", "addon"),
        ("alternative_comparison", "reasoning", "Comparação de alternativas", "Compara opções usando os mesmos critérios e explicita trade-offs.", "Decisões técnicas, editoriais ou estratégicas.", "Quando existe uma única solução permitida pelas restrições.", "Compare alternativas em critérios comuns, recomende uma e declare os trade-offs relevantes.", "medium", "addon"),
        ("risk_analysis", "reasoning", "Análise de riscos", "Identifica falhas, impactos, mitigação e reversibilidade.", "Mudanças destrutivas, segurança, produção ou decisões difíceis de reverter.", "Tarefas rotineiras de baixo impacto.", "Avalie probabilidade, impacto, mitigação e sinais verificáveis de cada risco material.", "medium", "addon"),
        ("independent_verification", "reasoning", "Verificação independente", "Exige validação separada da produção do resultado.", "Resultados importantes que podem ser testados ou confrontados com critérios.", "Quando não existe qualquer evidência externa possível.", "Valide o resultado com testes, fontes ou critérios independentes da alegação de quem o produziu.", "high", "addon"),
        ("software_implementation", "software", "Implementação de software", "Transforma a solicitação em trabalho de inspeção, alteração, testes e entrega.", "Criação ou alteração de funcionalidades em um workspace.", "Quando o usuário quer apenas explicação ou diagnóstico sem mudanças.", "Inspecione o workspace, preserve mudanças existentes, implemente o requisito, teste proporcionalmente ao risco e relate o resultado.", "medium", "primary"),
        ("bug_diagnosis", "software", "Diagnóstico de problema", "Estrutura sintomas, reprodução, comportamento esperado, evidências e causa raiz.", "Bugs, falhas intermitentes e incidentes técnicos.", "Quando o pedido já autoriza implementação e a causa está comprovada.", "Reproduza quando possível, reúna evidências, identifique a causa raiz e separe diagnóstico de correção.", "medium", "primary"),
        ("safe_refactoring", "software", "Refatoração segura", "Melhora a estrutura preservando comportamento e compatibilidade.", "Dívida técnica com comportamento existente que não pode mudar.", "Quando o objetivo principal é alterar o comportamento do produto.", "Caracterize o comportamento atual, faça mudanças incrementais e prove compatibilidade com testes.", "high", "primary"),
        ("test_driven", "software", "Orientada a testes", "Converte requisitos em testes e usa as falhas para dirigir a implementação.", "Regras de negócio, regressões e componentes verificáveis.", "Protótipos descartáveis ou resultados sem interface testável.", "Defina testes observáveis, veja-os falhar pela razão correta, implemente e execute a regressão relevante.", "high", "both"),
        ("security_review", "software", "Revisão de segurança", "Analisa fronteiras de confiança, entradas, permissões, segredos e abuso.", "Autenticação, dados sensíveis, integrações e superfícies públicas.", "Como substituto de auditoria especializada em sistemas críticos.", "Modele ameaças relevantes, valide controles existentes e priorize achados por impacto e explorabilidade.", "high", "primary"),
        ("performance_investigation", "software", "Investigação de performance", "Exige medição, perfil e comparação antes e depois.", "Latência, consumo de recursos ou problemas de escala.", "Quando não há sintoma mensurável nem ambiente representativo.", "Estabeleça baseline, localize o gargalo com dados, altere uma causa material e compare resultados.", "high", "primary"),
        ("react_tools", "agentic", "Raciocínio e uso de ferramentas", "Orienta alternância entre inspeção, ação com ferramentas e avaliação do resultado.", "Agentes com acesso a arquivos, comandos, busca ou APIs.", "Chats sem ferramentas ou tarefas puramente textuais.", "Use ferramentas para obter evidências e agir; reavalie o estado após cada resultado material sem expor raciocínio interno privado.", "medium", "both"),
        ("prompt_chaining", "agentic", "Encadeamento de prompts", "Organiza uma tarefa em estágios cujas saídas alimentam os próximos.", "Processos com fases distintas e contratos claros entre elas.", "Quando uma única instrução direta é suficiente.", "Defina estágios, entrada e saída de cada estágio e validações nas transições.", "high", "both"),
        ("implementation_loop", "agentic", "Loop de implementação", "Repete implementar, testar, criticar e corrigir até cumprir os critérios.", "Trabalho verificável por testes, renderização ou métricas.", "Sem critérios de parada ou com custo de execução imprevisível.", "Repita inspeção, implementação e verificação; encerre ao cumprir os critérios ou diante de bloqueio externo comprovado.", "high", "both"),
        ("evaluator_optimizer", "agentic", "Evaluator–Optimizer", "Separa geração e avaliação por uma rubrica, refinando as falhas encontradas.", "Conteúdo ou artefatos com critérios claros de qualidade.", "Quando não existe rubrica ou forma de avaliar melhorias.", "Gere uma versão, avalie-a contra a rubrica, corrija a maior lacuna e repita até o limiar definido.", "high", "both"),
        ("builder_critic", "agentic", "Builder–Critic", "Usa contextos separados para construir e criticar o artefato.", "Quando revisão independente reduz vieses do autor.", "Ambientes sem capacidade de múltiplos agentes ou contextos.", "Separe construtor e crítico; o crítico deve inspecionar o resultado real e devolver correções acionáveis.", "high", "addon"),
        ("parallel_specialists", "agentic", "Especialistas paralelos", "Distribui subtarefas independentes a especialistas e integra os resultados.", "Objetivos divisíveis com frentes realmente independentes.", "Trabalho sequencial ou alterações concorrentes nos mesmos arquivos.", "Paralelize apenas partes independentes, defina contratos e faça uma integração final coerente.", "high", "addon"),
        ("gauntlet_loop", "agentic", "Gauntlet Loop", "Compara componentes com uma referência concreta usando construtores e críticos independentes até atingir o padrão.", "Projetos agentic longos, verificáveis e com uma referência forte de qualidade.", "Correções pequenas, orçamento limitado ou ausência de padrão mensurável.", "Defina objetivo e barra concreta, decomponha o trabalho, use construtor e crítico independentes e repita enquanto o resultado perder para a referência.", "very_high", "primary"),
        ("human_in_loop", "agentic", "Human-in-the-loop", "Introduz aprovações humanas em decisões críticas ou irreversíveis.", "Mudanças destrutivas, decisões subjetivas e expansão relevante de escopo.", "Para interromper desnecessariamente ações rotineiras e reversíveis.", "Continue autonomamente dentro do escopo e solicite aprovação somente nos pontos críticos previamente definidos.", "medium", "addon"),
        ("grounded_research", "research", "Pesquisa fundamentada", "Baseia conclusões em fontes verificáveis e distingue evidência de inferência.", "Pesquisa técnica, atualidades e decisões importantes.", "Quando a tarefa deve usar exclusivamente contexto já fornecido.", "Pesquise fontes primárias, cite afirmações relevantes e marque claramente inferências e incertezas.", "high", "primary"),
        ("source_verification", "research", "Verificação de fontes", "Confirma autoria, data, escopo e suporte direto de cada fonte.", "Alegações sensíveis, atuais ou sujeitas a desinformação.", "Conhecimento estável que já possui fonte canônica fornecida.", "Prefira fontes primárias, confirme que cada uma sustenta a afirmação associada e registre divergências.", "medium", "addon"),
        ("uncertainty_analysis", "research", "Análise de incertezas", "Separa fatos, hipóteses, lacunas e nível de confiança.", "Dados incompletos ou decisões sob incerteza.", "Quando a resposta é determinística e diretamente verificável.", "Declare o que é conhecido, inferido e desconhecido; não transforme ausência de evidência em certeza.", "medium", "addon"),
        ("content_from_scratch", "content", "Conteúdo do zero", "Transforma uma ideia em briefing, estrutura e conteúdo adequado ao objetivo.", "Quando existe uma ideia, mas ainda não há rascunho completo.", "Quando o pedido é somente revisar um texto existente.", "Defina público, objetivo, formato, mensagem central, estrutura e chamada final antes de redigir.", "medium", "primary"),
        ("article_blog", "content", "Artigo ou blog", "Estrutura título, abertura, desenvolvimento, exemplos e conclusão.", "Conteúdo editorial longo ou educativo.", "Posts curtos ou documentação estritamente técnica.", "Produza um artigo coerente para o público e objetivo indicados, com seções úteis e sem preenchimento repetitivo.", "medium", "primary"),
        ("social_content", "content", "Conteúdo para redes sociais", "Adapta mensagem, extensão, gancho e chamada à plataforma escolhida.", "Posts, carrosséis, threads e campanhas sociais.", "Quando plataforma, público ou objetivo não podem ser inferidos.", "Adapte ao canal informado, crie gancho honesto, entregue valor e use uma chamada coerente com o objetivo.", "medium", "primary"),
        ("video_script", "content", "Roteiro de vídeo ou podcast", "Organiza gancho, cenas ou blocos, transições e encerramento.", "Vídeos, podcasts, aulas e apresentações narradas.", "Texto destinado apenas à leitura silenciosa.", "Crie roteiro falável com ritmo, marcações úteis, transições naturais e duração compatível.", "medium", "primary"),
        ("educational_content", "content", "Conteúdo educativo", "Ordena conceitos por dificuldade e usa exemplos e verificações de aprendizagem.", "Tutoriais, aulas, guias e onboarding.", "Quando o objetivo é apenas persuadir ou entreter.", "Defina pré-requisitos, explique progressivamente, use exemplos corretos e inclua forma de verificar compreensão.", "medium", "primary"),
        ("commercial_content", "content", "Conteúdo comercial", "Relaciona problema, benefício, evidência, objeções e chamada para ação.", "Landing pages, propostas, anúncios e campanhas.", "Comunicação neutra que não deve tentar converter.", "Seja persuasivo sem inventar resultados; conecte benefícios verificáveis às necessidades do público.", "medium", "primary"),
        ("storytelling", "content", "Storytelling", "Estrutura contexto, tensão, progressão e resolução ao redor de uma mensagem.", "Conteúdo que precisa gerar envolvimento e memorização.", "Relatórios normativos ou instruções que exigem máxima concisão.", "Construa narrativa coerente a serviço da mensagem, sem sacrificar precisão factual.", "medium", "both"),
        ("editorial_rewrite", "content", "Reescrita editorial", "Melhora ritmo, coesão e força narrativa preservando fatos e voz.", "Rascunhos de artigos, roteiros e comunicações institucionais.", "Quando o conteúdo precisa ser criado do zero.", "Reescreva com coesão e ritmo, preserve fatos, posicionamento e identidade autoral.", "medium", "primary"),
        ("audience_adaptation", "content", "Adaptação ao público", "Ajusta conhecimento pressuposto, exemplos e vocabulário ao leitor.", "O mesmo tema precisa atender públicos técnicos, executivos ou iniciantes.", "Quando o público não foi informado e não pode ser inferido.", "Adapte profundidade, exemplos e linguagem ao público sem distorcer o conteúdo.", "low", "addon"),
        ("content_repurposing", "content", "Reaproveitamento de conteúdo", "Converte uma fonte em outros formatos mantendo mensagem e fatos.", "Transformar artigo em posts, roteiro, newsletter ou resumo.", "Quando não existe conteúdo-fonte confiável.", "Preserve a mensagem central e adapte estrutura, extensão e chamada às convenções de cada formato.", "medium", "primary"),
        ("image_generation", "image", "Criação de imagem", "Estrutura sujeito, composição, enquadramento, ambiente, luz, cores, estilo e proporção.", "Gerar uma imagem nova a partir de uma descrição.", "Quando a intenção é editar uma imagem existente.", "Descreva sujeito, ação, composição, câmera, iluminação, paleta, ambiente, estilo, proporção e restrições visuais sem acumular adjetivos contraditórios.", "medium", "primary"),
        ("image_editing", "image", "Edição de imagem", "Separa claramente o que deve mudar do que precisa permanecer intacto.", "Alterar uma imagem fornecida preservando identidade, composição ou elementos específicos.", "Quando nenhuma imagem de referência foi fornecida ou pode ser anexada.", "Liste mudanças desejadas e invariantes; preserve explicitamente identidade, geometria, texto e regiões não mencionadas.", "medium", "primary"),
        ("visual_reference", "image", "Referência visual", "Usa referências para composição, acabamento ou qualidade sem copiar identidade indevidamente.", "Quando existe imagem, estilo ou padrão visual de comparação.", "Quando a referência não está disponível ao modelo destinatário.", "Explique quais propriedades da referência devem orientar o resultado e quais não devem ser copiadas.", "medium", "addon"),
        ("photographic_direction", "image", "Direção fotográfica", "Especifica lente, distância, ângulo, profundidade de campo, exposição e iluminação.", "Fotografia realista, produto, retrato ou cenas cinematográficas.", "Ilustrações em que terminologia fotográfica não agrega controle.", "Converta a intenção em direção fotográfica coerente, usando câmera e luz somente quando afetarem o resultado.", "medium", "addon"),
        ("image_text_layout", "image", "Imagem com texto e layout", "Define hierarquia, texto exato, posição, contraste e área segura.", "Cartazes, capas, anúncios, cards e interfaces com texto visível.", "Quando o gerador não oferece confiabilidade tipográfica suficiente e o texto pode ser aplicado depois.", "Preserve o texto exato entre delimitadores, defina hierarquia, alinhamento, contraste, margens e área segura.", "medium", "addon"),
        ("video_generation", "video", "Criação de vídeo", "Estrutura cena, duração, movimento, câmera, continuidade, ritmo, áudio e formato.", "Gerar um clipe ou sequência audiovisual nova.", "Quando o objetivo é apenas uma imagem estática.", "Defina sujeito, cenário, ações no tempo, câmera, duração, continuidade, ritmo, áudio, proporção e restrições por tomada.", "high", "primary"),
        ("video_storyboard", "video", "Storyboard e lista de planos", "Divide a narrativa em planos com objetivo, enquadramento, ação e transição.", "Vídeos com várias cenas ou narrativa que precisa de continuidade.", "Clipes simples de uma única tomada.", "Crie planos numerados com duração, enquadramento, ação, movimento de câmera, áudio e transição, mantendo continuidade.", "high", "primary"),
        ("video_editing", "video", "Edição e transformação de vídeo", "Define cortes, trechos preservados, ritmo, transições, áudio e resultado final.", "Editar, estender ou transformar um vídeo fornecido.", "Quando não há vídeo-fonte disponível.", "Use timecodes quando disponíveis, separe alterações de invariantes e especifique ritmo, continuidade e tratamento de áudio.", "high", "primary"),
        ("camera_motion", "video", "Movimento de câmera", "Controla trajetória, velocidade, estabilidade e relação da câmera com o sujeito.", "Cenas em que a câmera participa da narrativa.", "Quando câmera fixa é suficiente ou movimentos adicionais causariam inconsistência.", "Descreva um movimento de câmera fisicamente coerente por plano, incluindo início, trajetória, velocidade e término.", "medium", "addon"),
        ("temporal_continuity", "video", "Continuidade temporal", "Preserva identidade, direção, objetos, luz e causalidade entre quadros e cenas.", "Sequências, personagens recorrentes e transformações progressivas.", "Vídeos abstratos em que continuidade não é desejada.", "Declare invariantes visuais e temporais e descreva mudanças progressivas sem saltos não solicitados.", "high", "addon"),
    ]
    category_order = {name: pos for pos, name in enumerate(("text", "structure", "reasoning", "software", "agentic", "research", "content", "image", "video"))}
    counters: dict[str, int] = {}
    seed_rows = []
    for code, category, name, summary, when_to_use, when_to_avoid, template, effort, selection_mode in rows:
        counters[category] = counters.get(category, 0) + 1
        seed_rows.append({
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"forgehub:prompt-technique:{code}"),
            "code": code,
            "category": category,
            "name": name,
            "summary": summary,
            "when_to_use": when_to_use,
            "when_to_avoid": when_to_avoid,
            "instruction_template": template,
            "effort": effort,
            "selection_mode": selection_mode,
            "sort_order": category_order[category] * 100 + counters[category],
            "is_builtin": True,
            "is_active": True,
        })
    match_terms = {
        "clarity_objectivity": ["corrigir texto", "melhorar texto", "clareza", "objetividade", "reescrever"],
        "structured_prompt": ["estruturar prompt", "prompt completo", "requisitos", "critérios de aceite"],
        "software_implementation": ["implementar", "criar componente", "criar endpoint", "workspace", "código", "software", "funcionalidade"],
        "bug_diagnosis": ["bug", "erro", "falha", "não funciona", "diagnosticar", "causa raiz", "exception"],
        "safe_refactoring": ["refatorar", "refactoring", "dívida técnica", "preservar comportamento"],
        "test_driven": ["tdd", "orientado a testes", "testes primeiro", "regressão"],
        "security_review": ["segurança", "vulnerabilidade", "autenticação", "autorização", "ameaça", "secret"],
        "performance_investigation": ["performance", "desempenho", "latência", "lento", "memória", "cpu"],
        "implementation_loop": ["loop", "iterar até", "continue até", "não pare", "corrija e teste"],
        "gauntlet_loop": ["gauntlet", "barra de qualidade", "builder critic", "construtor e crítico"],
        "grounded_research": ["pesquisar", "fontes", "evidências", "referências", "estado da arte", "notícias"],
        "content_from_scratch": ["criar conteúdo", "conteúdo do zero", "campanha editorial", "briefing"],
        "article_blog": ["artigo", "blog", "post longo", "publicação"],
        "social_content": ["instagram", "linkedin", "rede social", "carrossel", "thread", "tweet"],
        "video_script": ["roteiro de vídeo", "roteiro para youtube", "podcast", "narração"],
        "educational_content": ["tutorial", "aula", "educativo", "ensinar", "onboarding"],
        "commercial_content": ["landing page", "anúncio", "vendas", "comercial", "conversão", "copywriting"],
        "storytelling": ["storytelling", "narrativa", "história", "personagem"],
        "image_generation": ["criar imagem", "gerar imagem", "ilustração", "fotografia", "logo", "ícone", "banner"],
        "image_editing": ["editar imagem", "alterar imagem", "remover da imagem", "trocar fundo", "preservar imagem"],
        "photographic_direction": ["lente", "câmera fotográfica", "profundidade de campo", "retrato", "produto"],
        "image_text_layout": ["cartaz", "pôster", "texto na imagem", "tipografia", "capa"],
        "video_generation": ["criar vídeo", "gerar vídeo", "clipe", "animação", "filmagem"],
        "video_storyboard": ["storyboard", "lista de planos", "shot list", "várias cenas"],
        "video_editing": ["editar vídeo", "cortar vídeo", "timecode", "transição de vídeo"],
        "temporal_continuity": ["continuidade", "mesmo personagem", "entre cenas", "consistência temporal"],
    }
    for row in seed_rows:
        row["match_terms"] = match_terms.get(row["code"], [])
    op.bulk_insert(
        techniques,
        seed_rows,
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_techniques_catalog", table_name="prompt_techniques", schema="company")
    op.drop_table("prompt_techniques", schema="company")
