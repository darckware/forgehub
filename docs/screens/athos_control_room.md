# Screen: Athos Control Room

> **Status:** proposta na arquitetura-alvo; ainda não implementada.

## Route & Purpose

Route: `/athos`.

Permite acompanhar Athos operando o ForgeHub, navegar pelo mesmo contexto, conversar pelo Assistant existente e controlar delegação, planejamento, liberação de Tasks e execuções.

## Layout

- Header com contexto, controller, Follow, Pause e Take Control.
- Athos Browser à esquerda.
- Assistant docked à direita.
- Activity timeline na região inferior.
- Mobile: tabs Browser, Assistant e Activity.

## Components

- `AthosControlRoomPage`
- `OperatorSessionHeader`
- `AthosBrowserPane`
- `AssistantPanel` extraído do drawer atual
- `OperatorActivityTimeline`
- `EligibleActionCard`
- `ApprovalActionCard`
- `ControllerTransferDialog`

## Data & API Calls

Contratos completos em `docs/modules/07_ATHOS_CONTROL_ROOM.md`.

## Business Rules

- Athos usa commands/APIs; browser apenas visualiza/navega.
- Somente actions backend elegíveis podem ser autorizadas.
- Tasks planned não são despacháveis.
- Pause/Take Control preserva histórico e reconcilia ações em andamento.
- Assistant pode preencher drafts, mas não salvar/aprovar silenciosamente.

## Dependencies

- AssistantDrawer/ChatPane refactor.
- Agent Athos identificável por profile slug.
- Operator session/action/focus backend.
- Delegation/Cockpit.
- ExecutionWave e orchestration para visualização completa.
