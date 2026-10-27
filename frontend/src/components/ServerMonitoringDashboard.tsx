import { type ReactNode, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Activity, Database, Globe, HardDrive, Network, ShieldCheck, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useServerMonitoring, type MonitoringSnapshot, type ProcessRow, type Source } from '@/hooks/useServerMonitoring';
import { useVpnStatus, type VpnStatus } from '@/hooks/useVpn';
import { useDockerUsage, type DockerUsage } from '@/hooks/useSystemControl';
import { useOffsiteBackupOverview, type OffsiteBackupOverview } from '@/hooks/useOffsiteBackup';

type ReadQuery<T> = {data?: T; isPending?: boolean; isError: boolean};
interface Props {snapshot?: MonitoringSnapshot; pending: boolean; failed: boolean; vpn: ReadQuery<VpnStatus>; backups: ReadQuery<OffsiteBackupOverview>; docker?: ReadQuery<DockerUsage> & {dataUpdatedAt?: number}}
const box = 'mb-4 min-w-0 break-inside-avoid md:mb-6';
export function ServerMonitoringDashboard() {
  const monitoring = useServerMonitoring();
  const vpn = useVpnStatus();
  const backups = useOffsiteBackupOverview();
  const docker = useDockerUsage({refetchInterval: 300_000});
  return <MonitoringPanels snapshot={monitoring.data} pending={monitoring.isPending} failed={monitoring.isError} vpn={vpn} backups={backups} docker={docker} />;
}

export function MonitoringPanels({snapshot: s, pending, failed, vpn, backups, docker}: Props) {
  const {t, i18n} = useTranslation('dashboard');
  const [sort, setSort] = useState<'by_memory' | 'by_cpu' | 'by_write'>('by_memory');
  const label = (key: string) => t(`monitor.${key}`);
  const bytes = (value: number | null | undefined) => {
    if (value == null) return '—';
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    const index = value > 0 ? Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4) : 0;
    return `${(value / 1024 ** index).toLocaleString(i18n.language, {maximumFractionDigits: 1})} ${units[index]}`;
  };
  const rate = (value: number | null | undefined) => value == null ? label('sampling') : `${bytes(value)}/s`;
  const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString(i18n.language) : '—';
  const stale = failed || (!!s && Date.now() - new Date(s.collected_at).getTime() > 60_000);
  const status = (source?: Source<unknown>) => {
    if (pending) return label('loading');
    const maxAge = (source === s?.directories || source === s?.directories.data?.docker_logs) ? 600_000 : 60_000;
    if ((stale && s) || (source?.collected_at && Date.now() - new Date(source.collected_at).getTime() > maxAge)) return label('stale');
    if (source?.refreshing && source.data) return label('refreshing');
    return source?.status === 'fresh' ? label('live') : source?.status === 'collecting' ? label('collecting') : label('unavailable');
  };
  const sourceFooter = (source?: Source<unknown>) => <p className={`mt-3 text-xs ${stale || source?.status === 'unavailable' ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}`}>
    {status(source)}{source?.collected_at ? ` · ${date(source.collected_at)}` : ''}
  </p>;
  const empty = (source?: Source<unknown>) => <p className="py-3 text-sm text-muted-foreground">{status(source)}</p>;
  const panel = (key: string, icon: ReactNode, children: ReactNode, footer?: ReactNode) => <div className={box} key={key}><Card>
    <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-lg">{icon}{label(key)}</CardTitle></CardHeader>
    <CardContent className="space-y-3 text-sm">{children}{footer}</CardContent>
  </Card></div>;
  const metric = (name: string, value: ReactNode) => <div className="min-w-0 rounded-md bg-muted/50 p-3"><p className="text-xs text-muted-foreground">{label(name)}</p><p className="mt-1 break-words font-semibold tabular-nums">{value}</p></div>;
  const table = (headers: string[], rows: ReactNode[][]) => <div className="max-h-80 overflow-auto rounded-md border" tabIndex={0} role="region" aria-label={headers.map(label).join(', ')}><table className="w-full text-left text-xs">
    <thead className="sticky top-0 bg-card"><tr>{headers.map(h => <th key={h} className="whitespace-nowrap border-b px-3 py-2 font-medium text-muted-foreground">{label(h)}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index} className="border-b last:border-0">{row.map((cell, col) => <td key={col} className="max-w-64 break-words px-3 py-2 align-top">{cell}</td>)}</tr>)}</tbody>
  </table></div>;
  const details = (name: string, children: ReactNode) => <details className="rounded-md border p-3"><summary className="cursor-pointer font-medium focus-visible:outline focus-visible:outline-2">{label(name)}</summary><div className="mt-3 space-y-3">{children}</div></details>;
  const truncated = (value?: boolean) => value ? <p className="text-xs text-muted-foreground">{label('truncated')}</p> : null;
  const mem = s?.memory.data;
  const processes = s?.processes.data;
  const access = s?.access.data;
  const units = s?.services.data;
  const containers = s?.containers.data;
  const fs = s?.filesystems.data;
  const timestampVpn = vpn.data?.checked_at;
  const vpnAvailable = !!vpn.data && vpn.data.backend_state !== 'Unavailable' && vpn.data.sources.some(source => source.name === 'status' && source.status === 'fresh');
  const vpnStale = vpn.isError || (!!timestampVpn && Date.now() - new Date(timestampVpn).getTime() > 60_000);
  const statusLabel = (value: string) => ['online','offline','needs_login','unavailable','ok','failed','running','queued','interrupted','accepted'].includes(value) ? label(value) : value;
  const processRows = (rows: ProcessRow[]) => rows.map(p => [<div><span className="font-medium">{p.name}</span><p className="text-muted-foreground">PID {p.pid} · {p.user}</p><p className="text-muted-foreground">{p.service || p.container_id || '—'}</p></div>, bytes(p.memory_bytes), p.cpu_percent == null ? '—' : `${p.cpu_percent}%`, rate(p.read_bytes_sec), rate(p.write_bytes_sec)]);
  return <>
    {panel('tailscale', <Globe className="h-5 w-5" />, <>
      {vpn.data && vpnAvailable ? <>
        <div className="grid grid-cols-2 gap-2">{metric('daemon', vpn.data.backend_state)}{metric('onlineHosts', vpn.data.peers.filter(p => p.online).length)}</div>
        <p className="break-words text-muted-foreground">{vpn.data.server.name || vpn.data.server.hostname} · {vpn.data.server.tailscale_ipv4 || '—'}</p>
        <p className="text-xs text-muted-foreground">{label('onlineHint')}</p>
        {table(['host','state','ip'], [...vpn.data.peers].sort((a,b) => Number(b.online)-Number(a.online)).map(p => [<div className="min-w-28"><p className="font-medium">{p.name || p.hostname || p.id}</p><p className="text-muted-foreground">{p.os || '—'} · {p.connection?.kind || '—'}{p.connection?.relay ? ` (${p.connection.relay})` : ''}</p><p className="text-muted-foreground">{label('lastSeen')}: {date(p.last_seen)}</p></div>, <div>{statusLabel(p.state)}{p.active && <p className="text-muted-foreground">{label('activeTraffic')}</p>}</div>, <span className="font-mono">{p.tailscale_ipv4 || '—'}</span>]))}
        {!!vpn.data.source_error && <p className="text-amber-600 dark:text-amber-400">{label('partial')}</p>}
      </> : <p className="text-muted-foreground">{vpn.isPending ? label('loading') : label('unavailable')}</p>}
      <Link to="/servers" className="inline-block text-primary underline underline-offset-4">{label('machines')}</Link>
    </>, <p className={`text-xs ${vpnStale ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}`}>{vpnStale && vpn.data ? label('stale') : vpnAvailable ? label('live') : label('unavailable')} · {date(timestampVpn)}</p>)}

    {panel('processes', <Activity className="h-5 w-5" />, <>
      {mem ? <div className="grid grid-cols-2 gap-2">{metric('available', bytes(mem.available_bytes))}{metric('cache', bytes(mem.cache_bytes))}{metric('swap', `${bytes(mem.swap_used_bytes)} / ${bytes(mem.swap_total_bytes)}`)}{metric('load', `${mem.load.map(x=>x.toFixed(2)).join(' · ')} / ${mem.cpu_count} CPU`)}</div> : empty(s?.memory)}
      {processes ? <>
        <div className="flex flex-wrap items-center justify-between gap-2"><p>{label('totalProcesses')}: <strong>{processes.total}</strong></p><label className="flex items-center gap-2 text-xs">{label('sort')}<select aria-label={label('sort')} className="rounded-md border bg-background px-2 py-1.5" value={sort} onChange={e => setSort(e.target.value as typeof sort)}><option value="by_memory">{label('ram')}</option><option value="by_cpu">CPU</option><option value="by_write">{label('write')}</option></select></label></div>
        {table(['process','ram','cpu','read','write'], processRows(processes[sort]))}
        {truncated(processes.truncated)}<p className="text-xs text-muted-foreground">{label('cpuHint')}{processes.skipped > 0 ? ` · ${label('skipped')}: ${processes.skipped}` : ''}</p>
      </> : empty(s?.processes)}
    </>, sourceFooter(s?.processes))}

    {panel('disk', <HardDrive className="h-5 w-5" />, <>
      {fs ? table(['mount','used','free','inodes'], fs.map(f => [<div>{f.mount}<p className="text-muted-foreground">{f.device}</p></div>, `${bytes(f.used_bytes)} / ${bytes(f.total_bytes)} (${f.percent_used ?? '—'}%)`, bytes(f.free_bytes), `${f.inodes_percent ?? '—'}%`])) : empty(s?.filesystems)}
      {fs?.some(f => (f.percent_used ?? 0) >= 85 || (f.inodes_percent ?? 0) >= 85) && <p className="text-amber-600 dark:text-amber-400">{label('diskAlert')}</p>}
      {details('directories', <>{s?.directories.data ? table(['directory','size'], s.directories.data.items.map(d => [<span className="font-mono">{d.path}</span>, d.bytes == null ? label('unavailable') : bytes(d.bytes)])) : empty(s?.directories)}<p className="text-xs text-muted-foreground">{label('directoryHint')}</p>{sourceFooter(s?.directories)}</>)}
      {details('dockerStorage', <>
        {docker?.data ? table(['category','size','reclaimable'], docker.data.types.map(d => [label(({Images:'images', Containers:'containers', 'Local Volumes':'volumes', 'Build Cache':'buildCache'} as Record<string,string>)[d.type] || 'other'), bytes(d.size), bytes(d.reclaimable)])) : <p>{docker?.isPending ? label('loading') : label('unavailable')}</p>}
        <p className="text-xs text-muted-foreground">{docker?.isError && docker.data ? label('stale') : docker?.data ? label('live') : label('unavailable')} · {date(docker?.dataUpdatedAt ? new Date(docker.dataUpdatedAt).toISOString() : null)}</p>
        <p className="font-medium">{label('dockerLogs')}</p>
        {s?.directories.data?.docker_logs.data ? table(['container','size','driver'], s.directories.data.docker_logs.data.items.map(log => [log.container, bytes(log.bytes), log.driver])) : empty(s?.directories.data?.docker_logs)}
        {sourceFooter(s?.directories.data?.docker_logs)}
        <p className="text-xs text-muted-foreground">{label('logHint')}</p>
      </>)}
      <p className="text-xs text-muted-foreground">{label('diskHint')}</p>
    </>, sourceFooter(s?.filesystems))}

    {panel('network', <Network className="h-5 w-5" />, <>
      {s?.network.data ? table(['interface','receive','send','errors'], s.network.data.map(n => [<span className="font-mono">{n.interface}</span>, rate(n.rx_bytes_sec), rate(n.tx_bytes_sec), `${n.rx_errors + n.tx_errors} / ${n.rx_dropped + n.tx_dropped}`])) : empty(s?.network)}
      {details('connections', <>
        {s?.connections.data ? <><p>{label('totalConnections')}: <strong>{s.connections.data.total}</strong></p>{table(['remote','local','state','process'], s.connections.data.items.map(c => [<span className="font-mono">{c.remote_ip}:{c.remote_port}</span>, <span className="font-mono">{c.local_ip}:{c.local_port}</span>, `${c.protocol} · ${c.state}`, `${c.process || '—'}${c.pid ? ` (${c.pid})` : ''}`]))}{truncated(s.connections.data.truncated)}</> : empty(s?.connections)}
        <p className="text-xs text-muted-foreground">{label('connectionHint')}</p>{sourceFooter(s?.connections)}
      </>)}
    </>, sourceFooter(s?.network))}

    {panel('access', <Users className="h-5 w-5" />, <>
      <p className="font-medium">{label('sessions')}</p>
      {access?.sessions.data ? access.sessions.data.length ? table(['user','terminal','origin','since'], access.sessions.data.map(a => [a.user, a.terminal, a.source || '—', a.since])) : <p className="text-muted-foreground">{label('noSessions')}</p> : empty(access?.sessions)}
      {sourceFooter(access?.sessions)}
      {details('sshEvents', <>{access?.ssh_events.data ? <>{access.ssh_events.data.items.length ? table(['time','state','user','ip'], access.ssh_events.data.items.map(e => [date(e.at), statusLabel(e.result), e.user, <span className="font-mono">{e.ip}</span>])) : <p>{label('noEvents')}</p>}{truncated(access.ssh_events.data.truncated)}</> : empty(access?.ssh_events)}{sourceFooter(access?.ssh_events)}</>)}
      <p className="text-xs text-muted-foreground">{label('accessHint')}</p>
    </>, sourceFooter(s?.access))}

    {panel('services', <ShieldCheck className="h-5 w-5" />, <>
      {units ? <>{units.system.data && table(['service','state'], units.system.data.map(u => [u.name, `${u.load} · ${u.state} / ${u.substate}`]))}{sourceFooter(units.system)}{units.user.data && table(['service','state'], units.user.data.map(u => [u.name, `${u.load} · ${u.state} / ${u.substate}`]))}{sourceFooter(units.user)}</> : empty(s?.services)}
      {details('containers', <>
        {containers ? <>{table(['service','state'], containers.states.map(c => [c.Names, `${c.State} · ${c.Status}`]))}{table(['container','cpu','ram','io'], containers.usage.map(c => [<div>{c.Name}<p className="text-muted-foreground">{c.PIDs} PID</p></div>, c.CPUPerc, `${c.MemUsage} (${c.MemPerc})`, c.BlockIO]))}{truncated(containers.truncated)}<p className="text-xs text-muted-foreground">{label('containerHint')}</p></> : empty(s?.containers)}{sourceFooter(s?.containers)}
      </>)}
      <p className="text-xs text-muted-foreground">{label('serviceHint')}</p>
    </>, sourceFooter(s?.services))}

    {panel('backups', <Database className="h-5 w-5" />, <>
      {backups.data ? <>
        {backups.data.targets.length ? table(['target','lastRun','lastSuccess'], backups.data.targets.map(target => [<div className="min-w-24">{target.label}<p className="text-muted-foreground">{target.enabled ? label('enabled') : label('disabled')}</p></div>, <div className={target.last_run?.status === 'failed' || target.last_run?.status === 'interrupted' ? 'font-medium text-destructive dark:text-red-400' : ''}>{target.last_run ? statusLabel(target.last_run.status) : label('noBackup')}<p className="text-muted-foreground">{date(target.last_run?.finished_at || target.last_run?.started_at)}</p></div>, <div>{date(target.last_success?.finished_at)}<p className="font-mono text-muted-foreground">{target.last_success?.snapshot_id?.slice(0,12) || label('noSnapshot')}</p></div>])) : <p>{label('noTargets')}</p>}
        {backups.data.schedule_error && <p className="text-amber-600 dark:text-amber-400">{label('scheduleAlert')}</p>}
        <p className="text-xs text-muted-foreground">{label('backupHint')}</p>
      </> : <p className="text-muted-foreground">{backups.isPending ? label('loading') : label('unavailable')}</p>}
      {backups.isError && backups.data && <p className="text-amber-600 dark:text-amber-400">{label('stale')}</p>}
      <Link to="/system-control" className="inline-block text-primary underline underline-offset-4">{label('backupDetails')}</Link>
    </>)}
  </>;
}
