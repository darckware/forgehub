import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import "@/i18n";
import { useAuthStore, type AuthUser } from "@/store/authStore";
import { RequireAdmin } from "./RequireAdmin";

const user = (isAdmin: boolean): AuthUser => ({
  id: "11111111-1111-4111-8111-111111111111",
  username: isAdmin ? "admin" : "operator",
  email: null,
  full_name: null,
  avatar_data_url: null,
  totp_enabled: false,
  is_active: true,
  is_admin: isAdmin,
  profile_id: null,
  ui_language: "pt-BR",
});

function renderGuard(isAdmin: boolean) {
  useAuthStore.setState({ user: user(isAdmin) });
  render(
    <MemoryRouter initialEntries={["/vpn"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<p>Painel</p>} />
        <Route path="/vpn" element={<RequireAdmin><p>Controle VPN</p></RequireAdmin>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAdmin", () => {
  it("allows administrators", () => {
    renderGuard(true);
    expect(screen.getByText("Controle VPN")).toBeInTheDocument();
  });

  it("rejects direct navigation by non-administrators", () => {
    renderGuard(false);
    expect(screen.getByRole("heading", { name: "Acesso negado" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao painel" })).toHaveAttribute("href", "/");
    expect(screen.queryByText("Controle VPN")).not.toBeInTheDocument();
  });
});
