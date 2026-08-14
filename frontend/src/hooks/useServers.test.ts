import { describe, expect, it } from "vitest";
import { buildSshCommand, resolveLiveServer, type Server } from "./useServers";

function server(overrides: Partial<Server> = {}): Server {
  return {
    id: "1",
    name: "srv-app02",
    ip_address: "172.15.2.3",
    remote_user: "aegis",
    ssh_port: 22,
    ssh_key_path: null,
    public_key: null,
    private_key_stored: false,
    description: null,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("buildSshCommand", () => {
  it("uses the key on file when the row has one", () => {
    const command = buildSshCommand(server({ ssh_key_path: "/root/.ssh/id_ed25519_aegis" }));
    expect(command).toBe("ssh -i /root/.ssh/id_ed25519_aegis aegis@172.15.2.3");
  });

  it("never disables pubkey auth when the row has no key", () => {
    // Regression (2026-08-14): a NULL ssh_key_path means "ForgeHub does not
    // know of a key", not "the host has none" -- every inventory row is NULL
    // because HermesOps installs keys through ~/.ssh/config instead. Sending
    // PubkeyAuthentication=no turned a working key login into a password
    // prompt for an account that accepts no password.
    const command = buildSshCommand(server());
    expect(command).not.toContain("PubkeyAuthentication=no");
    expect(command).toBe(
      "ssh -o PasswordAuthentication=yes -o BatchMode=no aegis@172.15.2.3",
    );
  });

  it("carries a non-default port", () => {
    expect(buildSshCommand(server({ ssh_port: 2222 }))).toContain("-p 2222");
  });
});

describe("resolveLiveServer", () => {
  it("prefers the refetched row over the one the dialog captured", () => {
    // Regression (2026-08-14): the edit dialog held the Server object it was
    // opened with, so storing a key updated the cache while the vault section
    // kept rendering "No copy stored" until the dialog was reopened.
    const captured = server({ private_key_stored: false });
    const refetched = server({ private_key_stored: true });
    expect(resolveLiveServer([refetched], captured).private_key_stored).toBe(true);
  });

  it("keeps the captured row while the list is still loading", () => {
    const captured = server({ public_key: "ssh-ed25519 AAAA…" });
    expect(resolveLiveServer(undefined, captured)).toBe(captured);
  });

  it("keeps the captured row when it is no longer in the list", () => {
    const captured = server({ id: "gone" });
    expect(resolveLiveServer([server({ id: "other" })], captured)).toBe(captured);
  });
});
