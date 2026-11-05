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
