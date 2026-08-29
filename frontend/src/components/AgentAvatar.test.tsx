import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AgentAvatar,
  agentInitials,
  validateAgentAvatar,
} from "./AgentAvatar";


describe("AgentAvatar", () => {
  it("shows stable initials when the agent has no photo", () => {
    render(<AgentAvatar name="Hermes UX" avatarDataUrl={null} />);

    expect(screen.getByText("HU")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders the uploaded image when present", () => {
    render(
      <AgentAvatar
        name="Athos"
        avatarDataUrl="data:image/png;base64,iVBORw0KGgo="
        imageAlt="Foto de Athos"
      />,
    );

    expect(screen.getByRole("img", { name: "Foto de Athos" })).toHaveAttribute(
      "src",
      "data:image/png;base64,iVBORw0KGgo=",
    );
  });
});

describe("agentInitials", () => {
  it("uses at most the first two words", () => {
    expect(agentInitials("  Hermes   UX Agent ")).toBe("HU");
    expect(agentInitials("Athos")).toBe("A");
  });
});

describe("validateAgentAvatar", () => {
  it("accepts JPEG, PNG and WebP files up to 512 KiB", () => {
    for (const type of ["image/jpeg", "image/png", "image/webp"]) {
      expect(validateAgentAvatar(new File(["image"], "agent", { type }))).toBeNull();
    }
  });

  it("rejects unsupported, empty and oversized files with stable reason codes", () => {
    expect(validateAgentAvatar(new File(["gif"], "agent.gif", { type: "image/gif" }))).toBe("type");
    expect(validateAgentAvatar(new File([], "empty.png", { type: "image/png" }))).toBe("empty");
    expect(
      validateAgentAvatar(
        new File([new Uint8Array(512 * 1024 + 1)], "large.png", { type: "image/png" }),
      ),
    ).toBe("size");
  });
});
