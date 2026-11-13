import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import '@/i18n';
import i18n from '@/i18n';
import { ApiError, apiClient } from '@/lib/api';
import { MemoryRouter } from 'react-router-dom';
import { MoodleApprovalPanel } from './MoodleApprovalPanel';
vi.mock('@/hooks/useAgent', () => ({ useAgents: () => ({ data: [{ id: 'maia', name: 'Maia' }, { id: 'sender', name: 'Sender' }, { id: 'athos', name: 'Athos' }] }), useStreamTelegramImprovePrompt: () => vi.fn() }));
vi.mock('@/components/chat/ImprovePromptDialog', () => ({ ImprovePromptDialog: ({ initialDraft, onApply, onClose }: { initialDraft: string; onApply: (s: string) => void; onClose: () => void }) => <div role='dialog'><span>{initialDraft}</span><button onClick={() => onApply('Sugestão')}>Aplicar sugestão</button><button onClick={onClose}>Fechar melhoria</button></div> }));
const items = [{ request_id: 'r1', message_id: 'm1', number: 7, summary: 'Excluir curso X', operation: 'delete', environment: 'production', host: 'moodle.example', params: { courseid: 42 }, destructive: true, params_hash: 'hash', message_updated_at: '2026-01-01', expires_at: '2027-01-01' }];
const post = vi.spyOn(apiClient, 'post');
beforeEach(async () => { await i18n.changeLanguage('pt-BR'); vi.spyOn(apiClient, 'get').mockResolvedValue({ items }); post.mockReset(); localStorage.clear(); });
function open() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><MoodleApprovalPanel /></MemoryRouter></QueryClientProvider>); }
const batch = [{ request_id: 'r1', message_id: 'm1', params_hash: 'hash', message_updated_at: '2026-01-01' }];
it('approves with one button after showing what will run, with no password or link', async () => {
  post.mockResolvedValue({ approved: [7] }); open(); await screen.findByText(/.Excluir curso X/);
  expect(screen.getByLabelText('Agente executor')).toHaveValue('maia');
  fireEvent.change(screen.getByLabelText('Instrução para o executor'), { target: { value: 'Verifique primeiro' } });
  fireEvent.click(screen.getByRole('button', { name: 'Aprovar #7' }));
  const dialog = screen.getByRole('dialog'); expect(within(dialog).getByText(/moodle.example/)).toBeInTheDocument(); expect(within(dialog).getByText(/courseid/)).toHaveTextContent('42');
  expect(within(dialog).queryByLabelText(/senha/i)).not.toBeInTheDocument(); expect(post).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Aprovar operação' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/personal/moodle-approvals/authorize', { executor_agent_id: 'maia', instruction: 'Verifique primeiro', items: batch }));
  await screen.findByText('Operações autorizadas. A execução será acompanhada abaixo.');
});
it('rejects with an optional reason', async () => {
  post.mockResolvedValue({ rejected: [7] }); open(); await screen.findByText(/.Excluir curso X/);
  fireEvent.click(screen.getByRole('button', { name: 'Recusar #7' }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Motivo (opcional)'), { target: { value: 'Pedido errado' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Recusar' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/personal/moodle-approvals/reject', { reason: 'Pedido errado', items: batch }));
  await screen.findByText('Solicitações recusadas.');
});
it('reports a failure and keeps the selection', async () => {
  post.mockRejectedValue(new Error('falhou')); open(); await screen.findByText(/.Excluir curso X/);
  fireEvent.click(screen.getByRole('checkbox', { name: /Selecionar #7/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Aprovar #7' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Aprovar operação' }));
  await screen.findByText('Não foi possível concluir. Atualize a lista e tente novamente.');
  expect(screen.getByRole('checkbox', { name: /Selecionar #7/ })).toBeChecked();
});
it('does nothing when the confirmation is cancelled', async () => {
  open(); await screen.findByText(/.Excluir curso X/);
  fireEvent.click(screen.getByRole('button', { name: 'Recusar #7' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancelar' }));
  expect(post).not.toHaveBeenCalled();
});

it('keeps instruction until the Athos suggestion is applied', async () => {
  open(); await screen.findByText(/.Excluir curso X/);
  const field = screen.getByLabelText('Instrução para o executor');
  fireEvent.change(field, { target: { value: 'Original' } });
  fireEvent.click(screen.getByRole('button', { name: 'Melhorar instrução com Athos' }));
  expect(field).toHaveValue('Original');
  fireEvent.click(screen.getByRole('button', { name: 'Fechar melhoria' }));
  expect(field).toHaveValue('Original');
  fireEvent.click(screen.getByRole('button', { name: 'Melhorar instrução com Athos' }));
  fireEvent.click(screen.getByRole('button', { name: 'Aplicar sugestão' }));
  expect(field).toHaveValue('Sugestão');
});


it('distinguishes a disabled feature from an empty approval queue', async () => {
  vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError('disabled', 503, {}));
  open();
  await screen.findByText('Aprovações Moodle indisponíveis neste ambiente.');
  expect(screen.queryByText('Nenhuma solicitação pendente.')).not.toBeInTheDocument();
});

it('authorizes the exact selected batch once and preserves each approval identifier', async () => {
  const other = { ...items[0], request_id: 'r2', message_id: 'm2', number: 8, summary: 'Outra operação', params_hash: 'otherhash' };
  vi.spyOn(apiClient, 'get').mockResolvedValue({ items: [items[0], other] });
  post.mockResolvedValue({ approved: [7, 8] }); open(); await screen.findByText(/.Excluir curso X/);
  fireEvent.click(screen.getByRole('checkbox', { name: /Selecionar #7/ }));
  fireEvent.click(screen.getByRole('checkbox', { name: /Selecionar #8/ }));
  fireEvent.click(screen.getByRole('button', { name: /Aprovar selecionadas/ }));
  const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Aprovar operação' });
  fireEvent.click(confirm); fireEvent.click(confirm);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenCalledWith('/api/v1/personal/moodle-approvals/authorize', expect.objectContaining({ items: [...batch, { request_id: 'r2', message_id: 'm2', params_hash: 'otherhash', message_updated_at: '2026-01-01' }] }));
});

it('shows a completed Moodle operation separately from a failed runner report', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ items: [], activity: [{ number: 9, message_id: 'm9', state: 'finished', outcome: 'completed', dispatch_status: 'failed' }] });
  open();
  await screen.findByText('Operação concluída no Moodle');
  expect(screen.getByText('O relatório de acompanhamento falhou; isso não desfaz a operação Moodle.')).toBeInTheDocument();
});
const studentBatch = { total: 3, new_accounts: 2, existing: 1, account_only: 1, units: ['CASA TESTE'], courses: ['IBA'], groups: ['CASA TESTE - T601M/26 IBA'],
  rows: [
    { row: 1, action: 'create', full_name: 'ANA LUÍSA DOS REIS', firstname: 'ANA', lastname: 'LUÍSA DOS REIS', username: 'analuisa17012014', email: 'analuisa17012014@gmail.com', userid: null, course: 'IBA', group: 'CASA TESTE - T601M/26 IBA', account_only: false, corrected_fields: ['firstname'], possible_duplicate_of: [] },
    { row: 2, action: 'create', full_name: 'DUDA REIS', firstname: 'DUDA', lastname: 'REIS', username: 'dudareis07082013', email: 'dudareis07082013@gmail.com', userid: null, course: null, group: null, account_only: true, corrected_fields: [], possible_duplicate_of: [{ id: 61, username: 'dudaoutra' }] },
    { row: 3, action: 'existing', full_name: 'BIA REIS', firstname: null, lastname: null, username: 'biareis', email: null, userid: 12, course: 'IBA', group: 'CASA TESTE - T601M/26 IBA', account_only: false, corrected_fields: [], possible_duplicate_of: [] },
  ],
  held_rows: [{ row: 4, full_name: 'CAIO REIS', candidates: [{ id: 60, username: 'caiooutro' }] }],
  rejected_rows: [{ row: 5, label: 'MADONNA', code: 'single_word_name', reason: 'Nome com uma palavra só' }] };
it('shows a student batch in readable form, with the list on opening and no raw parameters', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ items: [{ ...items[0], summary: 'Lote de 3 alunos', operation: 'mcp_student_batch_v1', destructive: false, params: {}, batch: studentBatch }] });
  open(); await screen.findByText(/Lote de 3 alunos/);
  expect(screen.getByText(/Contas novas: 2/)).toBeInTheDocument();
  expect(screen.getByText(/Só conta, sem matrícula nem turma: 1/)).toBeInTheDocument();
  expect(screen.getByText(/Unidade: CASA TESTE/)).toBeInTheDocument();
  expect(screen.getByText(/Retidas por possível duplicidade, não executam: 1/)).toBeInTheDocument();
  expect(screen.getByText(/MADONNA: Nome com uma palavra só/)).toBeInTheDocument();
  expect(screen.getByText(/analuisa17012014 · analuisa17012014@gmail.com/)).toBeInTheDocument();
  expect(screen.getByText(/ANA \/ LUÍSA DOS REIS/)).toBeInTheDocument();
  expect(screen.getByText(/Corrigido pela regra: firstname/)).toBeInTheDocument();
  expect(screen.getByText(/Sem matrícula e sem turma/)).toBeInTheDocument();
  fireEvent.click(screen.getAllByText('Ver alunos')[0]);
  expect(screen.getByRole('checkbox', { name: /Selecionar #7/ })).not.toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Aprovar #7' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText(/Contas novas: 2/)).toBeInTheDocument();
  expect(within(dialog).queryByText(/Parâmetros/)).not.toBeInTheDocument();
});

it('shows what a suspension does from the generated view, above the agent summary', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ items: [{ ...items[0], summary: 'Liberar o acesso do aluno', operation: 'core_user_update_users', destructive: false, params: { users: [{ id: 11, suspended: 1 }] }, operation_view: { kind: 'suspend_user', user_id: 11 } }] });
  open();
  const line = await screen.findByText('Suspender o usuário Moodle id 11');
  expect(screen.getByText('A suspensão encerra as sessões abertas desse usuário.')).toBeInTheDocument();
  const summary = screen.getByText('Descrição do agente: Liberar o acesso do aluno');
  expect(line.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Aprovar #7' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText('Suspender o usuário Moodle id 11')).toBeInTheDocument();
  expect(within(dialog).getByText('Descrição do agente: Liberar o acesso do aluno')).toBeInTheDocument();
});

it('describes a reactivation and an account confirmation', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ items: [
    { ...items[0], summary: 'Reativar', operation: 'core_user_update_users', destructive: false, params: { users: [{ id: 12, suspended: 0 }] }, operation_view: { kind: 'reactivate_user', user_id: 12 } },
    { ...items[0], request_id: 'r2', message_id: 'm2', number: 8, summary: 'Confirmar contas', operation: 'local_moodle_accounts_confirm_users', destructive: false, params: { userids: [30, 31, 32] }, operation_view: { kind: 'confirm_accounts', user_ids: [30, 31, 32] } },
  ] });
  open();
  await screen.findByText('Reativar o usuário Moodle id 12');
  expect(screen.getByText('Confirmar 3 contas Moodle: ids 30, 31, 32')).toBeInTheDocument();
  expect(screen.queryByText('A suspensão encerra as sessões abertas desse usuário.')).not.toBeInTheDocument();
});
