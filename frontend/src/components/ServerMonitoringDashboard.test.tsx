import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { MonitoringPanels } from './ServerMonitoringDashboard';
import type { VpnStatus } from '@/hooks/useVpn';
import type { MonitoringSnapshot } from '@/hooks/useServerMonitoring';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'pt-BR' } }) }));
const unavailable = {status: 'unavailable', collected_at: null, error: 'source', data: null};
const sample = {
  collected_at: new Date().toISOString(), memory: unavailable, processes: unavailable, network: unavailable,
  connections: unavailable, filesystems: unavailable, directories: unavailable, access: unavailable,
  services: unavailable, containers: unavailable,
} as MonitoringSnapshot;
function show(data?: MonitoringSnapshot, error = false) {
  return render(<MemoryRouter><MonitoringPanels snapshot={data} failed={error} pending={!data && !error} vpn={{isError: true}} backups={{isError: true}} /></MemoryRouter>);
}
describe('live monitoring source states', () => {
  it('shows loading rather than zero processes or connections', () => {
    show();
    expect(screen.getAllByText('monitor.loading').length).toBeGreaterThan(0);
    expect(screen.queryByText('0 B/s')).not.toBeInTheDocument();
  });
  it('marks failed sources unavailable and never claims offline hosts or successful backups', () => {
    show(sample);
    expect(screen.getAllByText('monitor.unavailable').length).toBeGreaterThan(0);
    expect(screen.queryByText('monitor.online')).not.toBeInTheDocument();
    expect(screen.queryByText('monitor.ok')).not.toBeInTheDocument();
  });
  it('keeps previous data but explicitly marks a failed refresh stale', () => {
    show(sample, true);
    expect(screen.getAllByText('monitor.stale').length).toBeGreaterThan(0);
  });
});

it('does not turn a HTTP-200 unavailable VPN source into zero online hosts', () => {
  const vpn = {backend_state: 'Unavailable', server: {id:'self',name:null,hostname:null,dns_name:null,os:null,tags:[],tailscale_ipv4:null,state:'unavailable',online:false,active:false,last_seen:null,key_expiry:null,rx_bytes:0,tx_bytes:0,connection:null,daemon_state:null,posture:null}, peers: [], source_error: 'bridge_unavailable', sources: [{name: 'status', status: 'unavailable', checked_at: new Date().toISOString(), error_code: 'bridge_unavailable'}], checked_at: new Date().toISOString()} as VpnStatus;
  render(<MemoryRouter><MonitoringPanels snapshot={sample} pending={false} failed={false} vpn={{data: vpn, isError: false}} backups={{isError: true}} /></MemoryRouter>);
  expect(screen.queryByText('monitor.onlineHosts')).not.toBeInTheDocument();
});
it('checks directory freshness independently from the current snapshot', () => {
  const data = {...sample, directories: {status: 'fresh', collected_at: '2000-01-01T00:00:00Z', error: null, data: {items: [], docker_logs: unavailable}}} as MonitoringSnapshot;
  show(data);
  expect(screen.getAllByText(/monitor.stale/).length).toBeGreaterThan(0);
});
it('shows Docker occupancy categories with reclaimable sizes and log metadata', () => {
  const data = {...sample, directories: {status:'fresh', collected_at: sample.collected_at, error:null, data:{items:[], docker_logs:{status:'fresh',collected_at:sample.collected_at,error:null,data:{items:[{container:'db-local',driver:'json-file',bytes:1048576}],truncated:false}}}}} as MonitoringSnapshot;
  render(<MemoryRouter><MonitoringPanels snapshot={data} pending={false} failed={false} vpn={{isError:true}} backups={{isError:true}} docker={{isError:false,dataUpdatedAt:Date.now(),data:{disk:null,unused_images:[],types:[{type:'Local Volumes',size:1073741824,reclaimable:0,total_count:1,active:1}]}}} /></MemoryRouter>);
  expect(screen.getByText('monitor.volumes')).toBeInTheDocument();
  expect(screen.getByText('1 GiB')).toBeInTheDocument();
  expect(screen.getByText('db-local')).toBeInTheDocument();
  expect(screen.getByText('json-file')).toBeInTheDocument();
});
