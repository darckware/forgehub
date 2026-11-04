import { fireEvent, render, screen } from "@testing-library/react";
import { vi, it, expect } from "vitest";
import UserConnections from "./UserConnections";

const mutate = vi.fn();
vi.mock("./useUserConnections", () => ({
  useUserConnections: () => ({
    query: { data: [{ id: "session-1", is_active: true, is_current: true, expires_at: "2099-01-01T00:00:00Z", last_activity_at: "2026-01-01T00:00:00Z", ip_address: "127.0.0.1", user_agent: "Test browser", device_summary: "Test browser", agent_name: null }] },
    revoke: { mutate, isPending: false },
  }),
}));

it("confirms before ending a connection", () => {
  render(<UserConnections userId="user-1" />);
  expect(screen.getAllByText(/Test browser/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "users.connections.end" }));
  expect(mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "confirmDialog.defaultConfirm" }));
  expect(mutate).toHaveBeenCalledWith("session-1", expect.any(Object));
});
