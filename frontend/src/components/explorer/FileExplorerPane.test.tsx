import { fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { apiClient } from '@/lib/api';
import { FileExplorerPane } from './FileExplorerPane';

vi.mock('@/lib/api', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
  ApiError: class extends Error {},
}));

beforeEach(async () => {
  vi.clearAllMocks();
  await i18n.changeLanguage('pt-BR');
  vi.mocked(apiClient.get).mockImplementation(async (url) => url.endsWith('/quick-access') ? [] : {
    path: '/docs', parent: '/', entries: [
      { name: 'manual.zip', path: '/docs/manual.zip', type: 'file', size: 10, modified: 0, is_symlink: false },
      { name: 'notes.txt', path: '/docs/notes.txt', type: 'file', size: 2, modified: 0, is_symlink: false },
    ],
  });
  vi.mocked(apiClient.post).mockResolvedValue({ name: 'manual', path: '/docs/manual', type: 'dir' });
});

it('keeps the ZIP dialog open on conflict and allows a new destination name', async () => {
  vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('Destination already exists'));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FileExplorerPane initialPath="/docs" quickAccess={[]} active />
  </QueryClientProvider>);
  fireEvent.contextMenu(await screen.findByText('notes.txt'));
  expect(within(screen.getByRole('menu')).queryByRole('menuitem', { name: 'Extrair arquivo…' })).toBeNull();
  fireEvent.click(screen.getByRole('menuitem', { name: 'Compactar em ZIP…' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Compactar em ZIP…' }));
  await screen.findByText('Destination already exists');
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'another-name' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Compactar em ZIP…' }));
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/api/v1/file-explorer/compress',
    { paths: ['/docs/notes.txt'], destination: '/docs/another-name.zip' }, { params: {} }));
});

it('opens extraction from the Workspace context menu and uses the selected SSH server', async () => {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FileExplorerPane initialPath="/docs" quickAccess={[]} active server={{ id: 'server-1', name: 'Example' }} />
  </QueryClientProvider>);
  fireEvent.contextMenu(await screen.findByText('manual.zip'));
  const menu = screen.getByRole('menu');
  expect(within(menu).getByRole('menuitem', { name: 'Compactar em ZIP…' })).toBeVisible();
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Extrair arquivo…' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByRole('textbox')).toHaveValue('manual');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Extrair arquivo…' }));
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/api/v1/file-explorer/extract',
    { paths: ['/docs/manual.zip'], destination: '/docs/manual' }, { params: { server_id: 'server-1' } }));
});
