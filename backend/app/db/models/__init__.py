# domain model modules are imported here by the wiring step
from app.db.models.product import Product, ProductModule, ProductVersion, Release  # noqa: F401
from app.db.models.project import (  # noqa: F401
    Project,
    ProjectPlan,
    PlanBaseline,
    ChangeRequest,
    ProjectStructureNode,
    ProjectForgeRouterConfig,
)
from app.db.models.pipeline import (  # noqa: F401
    PipelineTemplate,
    PipelineTemplateStage,
    PipelineTemplateRequiredArtifact,
    ProjectPipeline,
    PipelineStage,
    PipelineStageDependency,
    PipelineStageRequiredArtifact,
    PipelineStageGate,
)
from app.db.models.backlog import (  # noqa: F401
    PlanningItem,
    FeatureRequest,
    BugReport,
    VersionScopeItem,
    TriageDecision,
)
from app.db.models.task import (  # noqa: F401
    ProjectTask,
    TaskDependency,
    TaskRequiredSkill,
    TaskAssignment,
    TaskExecution,
)
from app.db.models.agent import (  # noqa: F401
    Agent,
    AgentServiceCredential,
    SubAgent,
    Skill,
    AgentSkill,
    SubAgentSkill,
    AgentCostRate,
    AgentCapacity,
)
from app.db.models.artifact import Artifact, ArtifactVersion  # noqa: F401
from app.db.models.governance import (  # noqa: F401
    Policy, Approval, AuditEvent, PolicyVersion, PolicyBinding, PolicyEvaluation,
    ApprovalRequest, ApprovalDecisionRecord, AuthorityDelegation,
)
from app.db.models.chat import ChatSession, ChatMessage, ChatArtifact, ChatSessionParticipant  # noqa: F401
from app.db.models.toolversions import ToolVersionStatus, ToolSyncSetting  # noqa: F401
from app.db.models.cron_script import CronScript  # noqa: F401
from app.db.models.deploy import DeployInstallation, DeployGroup, DeploySyncIgnore  # noqa: F401
from app.db.models.profile import Profile, ProfilePermission, ProfileActionPermission  # noqa: F401
from app.db.models.user import User  # noqa: F401
from app.db.models.server import Server  # noqa: F401
from app.db.models.notification import Notification, NotificationIngestState  # noqa: F401
from app.db.models.tool import AgentTool  # noqa: F401
from app.db.models.audit import AuditCheck, AuditCheckRun  # noqa: F401
from app.db.models.doc_link import DocLink  # noqa: F401
from app.db.models.demand import AgentDemand, DemandAttachment, DemandGroup  # noqa: F401
from app.db.models.docs_area import DocsArea  # noqa: F401
from app.db.models.prompt_command import PromptCommand  # noqa: F401
from app.db.models.foundation_script import FoundationScript  # noqa: F401
from app.db.models.orchestration import (  # noqa: F401
    AgentRuntimeProfile,
    ProjectAgentMembership,
    ProjectLoopPolicy,
    TaskExecutionReview,
)
from app.db.models.system_scope import (  # noqa: F401
    DevelopmentRequest,
    ProductConcept,
    ProductConceptRevision,
    SystemBlueprint,
    SystemBlueprintRevision,
    SystemElement,
    SystemElementRevision,
    SystemElementRelation,
    ProjectScope,
    ProjectScopeItem,
    ScopeItemAcceptanceCriterion,
)
from app.db.models.progress import ProgressCheckpoint, StageCompletionAssessment  # noqa: F401
from app.db.models.execution import (  # noqa: F401
    ExecutionWave, ExecutionWaveTask, ExecutionWorkPackage, ExecutionRunner,
    ExecutionLease, ExecutionEvent, ExecutionResult,
)
from app.db.models.web_automation import StandaloneApp, WebAutomationRoutine, MacroInstructionSet  # noqa: F401
