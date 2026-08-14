"""expand prompt techniques for product development

Revision ID: 7d1351f999f2
Revises: 649a49c930d1
Create Date: 2026-08-14 17:29:08.900132

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7d1351f999f2"
down_revision: Union[str, Sequence[str], None] = "649a49c930d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_prompt_techniques_category", "prompt_techniques", schema="company", type_="check")
    op.create_check_constraint(
        "ck_prompt_techniques_category",
        "prompt_techniques",
        "category IN ('text','structure','reasoning','software','agentic','research','content','design','automation','image','video')",
        schema="company",
    )
    techniques = sa.table(
        "prompt_techniques",
        sa.column("id", sa.UUID()),
        sa.column("code", sa.String()),
        sa.column("category", sa.String()),
        sa.column("name", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("when_to_use", sa.Text()),
        sa.column("when_to_avoid", sa.Text()),
        sa.column("requirements", postgresql.JSONB()),
        sa.column("compatible_with", postgresql.JSONB()),
        sa.column("conflicts_with", postgresql.JSONB()),
        sa.column("match_terms", postgresql.JSONB()),
        sa.column("instruction_template", sa.Text()),
        sa.column("effort", sa.String()),
        sa.column("selection_mode", sa.String()),
        sa.column("template_version", sa.Integer()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_builtin", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        schema="company",
    )
    rows = [
        ("frontend_implementation", "software", "Implementação frontend", "Estrutura componentes, estados, responsividade, acessibilidade e integração com APIs.", "Interfaces web implementadas em um frontend existente ou novo.", "Quando o pedido é apenas criar o conceito visual sem código.", ["frontend", "react", "vue", "interface web", "componente", "css"], "Inspecione o padrão do frontend, modele estados e interação, implemente responsividade e acessibilidade e valide visual e funcionalmente.", "high", "primary"),
        ("backend_implementation", "software", "Implementação backend", "Estrutura domínio, regras, persistência, segurança, observabilidade e testes.", "Serviços, APIs, workers e regras de negócio no servidor.", "Quando o trabalho é exclusivamente visual ou de conteúdo.", ["backend", "servidor", "fastapi", "worker", "regra de negócio"], "Modele a regra no domínio correto, valide entradas e autorização, preserve transações e compatibilidade e cubra o comportamento com testes.", "high", "primary"),
        ("api_design", "software", "Design e implementação de API", "Define recursos, contratos, erros, autenticação, idempotência e evolução.", "Criar ou revisar APIs HTTP, eventos ou integrações.", "Quando não existe consumidor ou caso de uso definido.", ["api", "endpoint", "rest", "webhook", "contrato"], "Defina contrato a partir dos consumidores, semântica, validação, erros, autorização, idempotência, versionamento e testes de integração.", "high", "primary"),
        ("database_design", "software", "Modelagem e implementação de banco", "Transforma regras em entidades, relacionamentos, restrições, índices e migrations seguras.", "Modelagem relacional, consultas, migrations e integridade de dados.", "Quando o armazenamento não faz parte do problema.", ["banco de dados", "database", "tabela", "migration", "sql", "postgres"], "Modele invariantes no banco, escolha tipos e chaves coerentes, planeje índices e migration reversível e valide consultas e integridade.", "high", "primary"),
        ("full_stack_implementation", "software", "Implementação full stack", "Coordena frontend, backend, banco, contrato e verificação ponta a ponta.", "Funcionalidades completas que atravessam todas as camadas.", "Mudanças isoladas em apenas uma camada.", ["full stack", "aplicação completa", "frontend e backend", "ponta a ponta"], "Defina o fluxo ponta a ponta e o contrato entre camadas, implemente banco, backend e frontend de forma coerente e teste integração e experiência final.", "very_high", "primary"),
        ("product_conception", "design", "Concepção de produto", "Transforma uma ideia em problema, público, proposta, hipóteses, escopo e métricas.", "Criação de produto digital ou definição de uma nova solução.", "Quando requisitos e solução já estão aprovados para implementação.", ["criar produto", "novo produto", "concepção", "ideia de produto", "mvp"], "Defina problema, usuários, proposta de valor, hipóteses, diferenciais, jornada, escopo inicial, riscos e métricas antes de prescrever funcionalidades.", "high", "primary"),
        ("product_discovery", "design", "Descoberta e validação de produto", "Planeja pesquisa, hipóteses, experimentos e evidências para reduzir incerteza.", "Antes de investir em uma solução ou funcionalidade de alto risco.", "Quando a decisão já é mandatória e não depende de validação de mercado.", ["discovery", "validar produto", "pesquisa com usuário", "hipótese de produto"], "Liste hipóteses críticas, evidência necessária, pesquisa ou experimento de menor custo e critérios objetivos para decidir.", "high", "primary"),
        ("website_design", "design", "Design de site", "Define objetivo, arquitetura, páginas, hierarquia, conversão, responsividade e acessibilidade.", "Sites institucionais, landing pages, portais e experiências editoriais.", "Aplicações dominadas por fluxos complexos e estado operacional.", ["criar site", "design de site", "landing page", "site institucional", "portal"], "Estruture público, objetivo, mapa de páginas, hierarquia visual, conteúdo, componentes, responsividade, acessibilidade e critérios de conversão.", "high", "primary"),
        ("web_app_design", "design", "Design de aplicação web", "Modela jornadas, navegação, estados, dados, feedback e padrões de interação.", "Dashboards, sistemas internos, SaaS e aplicações web interativas.", "Sites predominantemente informativos sem fluxos de aplicação.", ["aplicação web", "web app", "dashboard", "saas", "sistema web"], "Mapeie usuários e jornadas, arquitetura de informação, telas, estados vazios/erro/loading, componentes, responsividade e acessibilidade.", "high", "primary"),
        ("mobile_app_design", "design", "Design de aplicação mobile", "Adapta jornadas a toque, telas pequenas, plataformas, navegação e uso móvel.", "Aplicativos iOS, Android, React Native ou Flutter.", "Experiências exclusivamente desktop.", ["aplicativo mobile", "app mobile", "ios", "android", "flutter", "react native"], "Projete jornadas mobile-first, navegação, gestos, ergonomia, estados offline, permissões, acessibilidade e convenções da plataforma.", "high", "primary"),
        ("ux_flow", "design", "Fluxo e experiência do usuário", "Desenha tarefas, decisões, feedback, exceções e recuperação ao longo da jornada.", "Fluxos de cadastro, compra, configuração e operações com várias etapas.", "Quando existe apenas uma peça visual sem interação.", ["ux", "jornada", "fluxo do usuário", "experiência do usuário", "wireframe"], "Descreva objetivo do usuário, caminho principal, decisões, estados, exceções, prevenção e recuperação de erros e sinais de sucesso.", "medium", "both"),
        ("design_system", "design", "Design system", "Define tokens, componentes, variantes, estados, acessibilidade e governança visual.", "Produtos com múltiplas telas ou equipes que precisam de consistência.", "Uma peça isolada sem perspectiva de reutilização.", ["design system", "componentes ui", "tokens", "biblioteca visual"], "Especifique princípios, tokens, componentes, variantes, estados, responsividade, acessibilidade, documentação e regras de evolução.", "high", "primary"),
        ("responsive_accessible_design", "design", "Design responsivo e acessível", "Inclui breakpoints, teclado, foco, contraste, semântica e tecnologias assistivas.", "Qualquer interface web ou mobile destinada a usuários reais.", "Nunca deve ser usado para justificar a remoção de requisitos visuais ou funcionais.", ["responsivo", "acessibilidade", "wcag", "mobile first", "teclado"], "Defina comportamento responsivo e critérios de acessibilidade observáveis para navegação, foco, contraste, semântica, conteúdo e movimento.", "medium", "addon"),
        ("brand_identity", "design", "Identidade de marca", "Estrutura posicionamento, personalidade, sistema visual, voz e aplicações.", "Criar ou revisar a identidade de um produto ou organização.", "Quando o pedido é apenas uma peça isolada sem contexto de marca.", ["identidade visual", "marca", "branding", "brand identity", "manual de marca"], "Defina público, posicionamento, atributos, voz, paleta, tipografia, linguagem visual, princípios de uso e aplicações consistentes.", "high", "primary"),
        ("logo_design", "design", "Criação de logomarca", "Cria um briefing visual para símbolo, wordmark, legibilidade e aplicações da marca.", "Conceituar ou gerar uma logomarca e suas variações.", "Quando ainda não há nome, posicionamento ou diferenciação mínima da marca.", ["logomarca", "logotipo", "logo", "símbolo da marca", "wordmark"], "Defina conceito, nome exato, atributos, símbolo/wordmark, geometria, legibilidade, escalabilidade, versões monocromáticas, fundos e usos; evite clichês e detalhes frágeis.", "high", "primary"),
        ("information_architecture", "design", "Arquitetura da informação", "Organiza conteúdo, navegação, hierarquia e rotulagem conforme o modelo mental do usuário.", "Sites e aplicações com muitas áreas, objetos ou conteúdos.", "Fluxos pequenos cuja navegação já é direta.", ["arquitetura da informação", "mapa do site", "sitemap", "navegação", "taxonomia"], "Modele objetos e tarefas, agrupe conteúdo, defina hierarquia, rótulos, navegação e caminhos alternativos e valide encontrabilidade.", "medium", "addon"),
        ("workflow_automation", "automation", "Automação de processos", "Modela gatilhos, etapas, decisões, estados, exceções e resultado de um processo automatizado.", "Processos repetitivos entre pessoas, sistemas e dados.", "Processos raros, altamente subjetivos ou sem regra estável.", ["automatizar processo", "automação de processo", "workflow", "fluxo automático"], "Mapeie gatilho, entradas, etapas, decisões, estados, saídas, idempotência, retries, compensação, observabilidade e intervenção humana.", "high", "primary"),
        ("integration_automation", "automation", "Automação de integrações", "Conecta APIs, eventos e dados com contratos e recuperação de falhas.", "Sincronização entre serviços, webhooks e pipelines de dados.", "Quando integração manual é intencional por controle ou baixo volume.", ["automatizar integração", "integração api", "webhook", "sincronizar sistemas", "etl"], "Defina sistemas, contratos, autenticação, mapeamento, gatilho, idempotência, limites, retries, dead-letter e reconciliação.", "high", "primary"),
        ("browser_automation", "automation", "Automação de navegador", "Descreve navegação, seletores resilientes, esperas, autenticação e evidências.", "Tarefas repetitivas em sites sem API adequada e testes end-to-end.", "Quando uma API oficial é disponível e mais confiável.", ["automação de navegador", "browser automation", "playwright", "selenium", "preencher site"], "Modele passos observáveis, seletores resilientes, esperas por estado, sessões, downloads, capturas, falhas e limites éticos do site.", "high", "primary"),
        ("scheduled_automation", "automation", "Rotina agendada", "Define calendário, timezone, concorrência, atrasos, reexecução e monitoramento.", "Jobs recorrentes, manutenção, relatórios e sincronizações.", "Quando a execução depende de um evento em tempo real.", ["agendamento", "cron", "rotina agendada", "executar todo dia", "scheduler"], "Defina agenda e timezone, exclusão ou concorrência, tolerância a atraso, idempotência, timeout, retry, alertas e recuperação.", "medium", "primary"),
        ("agent_automation", "automation", "Automação com agentes", "Combina objetivos, ferramentas, limites, memória, avaliações e escalonamento humano.", "Trabalho variável que exige interpretação e uso de ferramentas.", "Processos determinísticos que uma automação convencional resolve melhor.", ["agente autônomo", "automação com ia", "agente de ia", "agentic automation"], "Defina objetivo, autoridade, ferramentas, contexto, estado, limites, critérios de verificação, orçamento, parada e escalonamento humano.", "very_high", "primary"),
        ("low_code_automation", "automation", "Automação low-code/no-code", "Traduz o processo em nós, gatilhos, condições e integrações de uma plataforma visual.", "n8n, Make, Zapier e ferramentas semelhantes.", "Quando requisitos exigem controle, escala ou testes além da plataforma.", ["n8n", "make.com", "zapier", "low-code", "no-code"], "Especifique plataforma, gatilho, nós, credenciais por referência, transformações, condições, retries, logs, dados de teste e exportação segura.", "medium", "primary"),
    ]
    op.bulk_insert(techniques, [
        {
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"forgehub:prompt-technique:{code}"),
            "code": code,
            "category": category,
            "name": name,
            "summary": summary,
            "when_to_use": when_to_use,
            "when_to_avoid": when_to_avoid,
            "requirements": [],
            "compatible_with": [],
            "conflicts_with": [],
            "match_terms": match_terms,
            "instruction_template": template,
            "effort": effort,
            "selection_mode": selection_mode,
            "template_version": 1,
            "sort_order": 700 + position,
            "is_builtin": True,
            "is_active": True,
        }
        for position, (code, category, name, summary, when_to_use, when_to_avoid, match_terms, template, effort, selection_mode)
        in enumerate(rows, start=1)
    ])


def downgrade() -> None:
    codes = (
        "frontend_implementation", "backend_implementation", "api_design", "database_design",
        "full_stack_implementation", "product_conception", "product_discovery", "website_design",
        "web_app_design", "mobile_app_design", "ux_flow", "design_system",
        "responsive_accessible_design", "brand_identity", "logo_design", "information_architecture",
        "workflow_automation", "integration_automation", "browser_automation", "scheduled_automation",
        "agent_automation", "low_code_automation",
    )
    op.execute(
        sa.text("DELETE FROM company.prompt_techniques WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(codes), type_=postgresql.ARRAY(sa.String()))
        )
    )
    op.drop_constraint("ck_prompt_techniques_category", "prompt_techniques", schema="company", type_="check")
    op.create_check_constraint(
        "ck_prompt_techniques_category",
        "prompt_techniques",
        "category IN ('text','structure','reasoning','software','agentic','research','content','image','video')",
        schema="company",
    )
