import { describe, expect, it } from "vitest";
import type { Server } from "./useServers";
import { bucketByClient, countReadiness, type HostGroup, type HostReadinessEntry } from "./useHostInventory";

function machine(id: string, overrides: Partial<Server> = {}): Server {
  return {
    id, name: id, ip_address: "100.64.0.1", remote_user: "adm", ssh_port: 22, ssh_key_path: null,
    public_key: null, private_key_stored: false, key_passphrase_stored: false, access_enabled: true,
    description: null, kind: "workstation", os_family: "windows", admin_user: null,
    darckware_client_id: null, darckware_client_name: null, location: null, tailnet_node_id: null,
    tailnet_name: null, group_ids: [], created_at: "", updated_at: "", ...overrides,
  };
}

function group(id: string, clientId: string | null, clientName: string | null = null): HostGroup {
  return { id, name: id, darckware_client_id: clientId, darckware_client_name: clientName, description: null, server_ids: [], created_at: "", updated_at: "" };
}

describe("bucketByClient", () => {
  it("buckets workstations by client, sorted by name, client-less last, servers left out", () => {
    const buckets = bucketByClient(
      [
        machine("a", { darckware_client_id: "c2", darckware_client_name: "Zeta" }),
        machine("b"),
        machine("c", { darckware_client_id: "c1", darckware_client_name: "Alfa" }),
        machine("srv", { kind: "server" }),
      ],
      [group("g1", "c1", "Alfa"), group("g3", "c3", "Beta")],
    );
    expect(buckets.map((b) => b.clientName)).toEqual(["Alfa", "Beta", "Zeta", null]);
    expect(buckets[0].groups.map((g) => g.id)).toEqual(["g1"]);
    expect(buckets.flatMap((b) => b.machines.map((m) => m.id))).not.toContain("srv");
  });
});

describe("countReadiness", () => {
  it("counts ready/offline/attention and keeps unknown only in the total", () => {
    const entry = (server_id: string, readiness: HostReadinessEntry["readiness"]): [string, HostReadinessEntry] =>
      [server_id, { server_id, readiness, tailnet_online: null, ssh: null, detail: null }];
    const byId = new Map([
      entry("1", "ready"), entry("2", "offline"), entry("3", "not_prepared"),
      entry("4", "online_no_access"), entry("5", "unknown"),
    ]);
    expect(countReadiness(["1", "2", "3", "4", "5", "6"], byId)).toEqual({ total: 6, ready: 1, offline: 1, attention: 2 });
  });
});
