import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
export interface Source<T> { status: 'fresh' | 'unavailable' | 'collecting'; collected_at: string | null; error: string | null; refreshing?: boolean; data: T | null }
export interface ProcessRow { pid: number; name: string; user: string; memory_bytes: number; cpu_percent: number | null; read_bytes_sec: number | null; write_bytes_sec: number | null; container_id: string | null; service: string | null }
export interface NetworkRow { interface: string; rx_bytes: number; tx_bytes: number; rx_bytes_sec: number | null; tx_bytes_sec: number | null; rx_errors: number; tx_errors: number; rx_dropped: number; tx_dropped: number }
export interface SocketRow { protocol: string; state: string; local_ip: string; local_port: string; remote_ip: string; remote_port: string; pid: number | null; process: string | null }
export interface Filesystem {mount: string; device: string; total_bytes: number; used_bytes: number; free_bytes: number; percent_used: number | null; inodes_percent: number | null}
export interface Unit {name: string; scope: string; load: string; state: string; substate: string}
export interface MonitoringSnapshot {
  collected_at: string;
  memory: Source<{total_bytes: number; available_bytes: number; used_bytes: number; cache_bytes: number; swap_total_bytes: number; swap_used_bytes: number; percent_used: number; cpu_count: number; load: number[]}>;
  processes: Source<{total: number; skipped: number; truncated: boolean; by_memory: ProcessRow[]; by_cpu: ProcessRow[]; by_write: ProcessRow[]}>;
  network: Source<NetworkRow[]>;
  connections: Source<{total: number; truncated: boolean; items: SocketRow[]}>;
  filesystems: Source<Filesystem[]>;
  directories: Source<{items: {path: string; bytes: number | null; status: string}[]; docker_logs: Source<{items: {container: string; driver: string; bytes: number | null}[]; truncated: boolean}>}>;
  access: Source<{sessions: Source<{user: string; terminal: string; since: string; source: string | null}[]>; ssh_events: Source<{items: {at: string | null; result: string; user: string; ip: string}[]; window_minutes: number; truncated: boolean}>; application_events: Source<unknown>}>;
  services: Source<{system: Source<Unit[]>; user: Source<Unit[]>}>;
  containers: Source<{usage: {ID: string; Name: string; CPUPerc: string; MemUsage: string; MemPerc: string; BlockIO: string; NetIO: string; PIDs: string}[]; states: {ID: string; Names: string; State: string; Status: string}[]; truncated: boolean}>;
}
export function useServerMonitoring() {
  return useQuery<MonitoringSnapshot>({
    queryKey: ['server-monitoring'], queryFn: () => apiClient.get('/api/v1/system-stats/details'),
    staleTime: 10_000, refetchInterval: () => document.visibilityState === 'visible' ? 15_000 : false,
    refetchIntervalInBackground: false, retry: false,
  });
}
