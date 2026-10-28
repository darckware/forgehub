import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import '@/i18n';
import i18n from '@/i18n';
import { ApiError, apiClient } from '@/lib/api';
import { MoodleApprovalPanel } from './MoodleApprovalPanel';
vi.mock('@/hooks/useAgent', () => ({ useAgents: () => ({ data: [{ id: 'maia', name: 'Maia' }, { id: 'sender', name: 'Sender' }, { id: 'athos', name: 'Athos' }] }), useStreamTelegramImprovePrompt: () => vi.fn() }));
vi.mock('@/components/chat/ImprovePromptDialog', () => ({ ImprovePromptDialog: ({ initialDraft, onApply, onClose }: { initialDraft: string; onApply: (s: string) => void; onClose: () => void }) => <div role='dialog'><span>{initialDraft}</span><button onClick={() => onApply('Sugestão')}>Aplicar sugestão</button><button onClick={onClose}>Fechar melhoria</button></div> }));
const items = [{ request_id: 'r1', message_id: 'm1', number: 7, summary: 'Excluir curso X', operation: 'delete', environment: 'production', host: 'moodle.example', params: { courseid: 42 }, destructive: true, params_hash: 'hash', message_updated_at: '2026-01-01', expires_at: '2027-01-01' }];
const post = vi.spyOn(apiClient, 'post');
beforeEach(async () => { await i18n.changeLanguage('pt-BR'); vi.spyOn(apiClient, 'get').mockResolvedValue({ items }); post.mockReset(); localStorage.clear(); window.history.replaceState(null, '', '/personal#telegram_challenge=test-challenge'); });
function open() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MoodleApprovalPanel /></QueryClientProvider>); }
async function prepare() {
  open(); await screen.findByText(/.Excluir curso X/);
  fireEvent.click(screen.getByRole('checkbox', { name: /Selecionar #7/ }));
  expect(screen.getByRole('option', { name: 'Sender' })).toBeInTheDocument();
  expect(screen.getByLabelText('Agente executor')).toHaveValue('maia');
  fireEvent.change(screen.getByLabelText('Instrução para o executor'), { target: { value: 'Verifique primeiro' } });
  fireEvent.click(screen.getByRole('button', { name: 'Revisar autorização' }));
  fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'secret123' } });
}
it('confirms the selected batch with instruction and clears the password', async () => {
  post.mockResolvedValue({ approved: [7] }); await prepare();
  const dialog = screen.getByRole('dialog'); expect(within(dialog).getByText(/production/)).toBeInTheDocument(); expect(within(dialog).getByText(/moodle.example/)).toBeInTheDocument(); expect(within(dialog).getByText(/courseid/)).toHaveTextContent('42');
  expect(post).not.toHaveBeenCalled(); fireEvent.click(within(dialog).getByRole('button', { name: 'Autorizar selecionadas' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/personal/moodle-approvals/authorize', { password: 'secret123', telegram_challenge: 'test-challenge', executor_agent_id: 'maia', instruction: 'Verifique primeiro', items: [{ request_id: 'r1', message_id: 'm1', params_hash: 'hash', message_updated_at: '2026-01-01' }] }));
  expect(screen.queryByLabelText('Senha')).not.toBeInTheDocument(); expect(JSON.stringify(localStorage)).not.toContain('secret123');
});
it('clears the password on failure while retaining the selection', async () => {
  post.mockRejectedValue(new Error('secret123')); await prepare(); fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Autorizar selecionadas' }));
  await screen.findByText('Não foi possível autorizar. Confira os itens e tente novamente.');
  expect(screen.queryByLabelText('Senha')).not.toBeInTheDocument(); expect(screen.getByRole('checkbox', { name: /Selecionar #7/ })).toBeChecked(); expect(screen.queryByText('secret123')).not.toBeInTheDocument();
});
it('clears the password when review is cancelled', async () => {
  await prepare();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancelar' }));
  expect(screen.queryByLabelText('Senha')).not.toBeInTheDocument();
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

it('removes the challenge from the URL and requests a new link explicitly', async () => {
  post.mockResolvedValue({ sent: true }); open(); await screen.findByText(/.Excluir curso X/);
  await waitFor(() => expect(window.location.hash).toBe(''));
  fireEvent.click(screen.getByRole('button', { name: 'Solicitar link no Telegram' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/personal/moodle-approvals/telegram-challenge'));
});

it('keeps the approvals panel hidden while the server feature flag is off', async () => {
  vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError('disabled', 503, {}));
  open();
  await waitFor(() => expect(screen.queryByText('Aprovações Moodle')).not.toBeInTheDocument());
});
