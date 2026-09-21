import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SecretBadge } from "./SecretBadge";
import { parseSecretSegments, Markdown } from "@/components/Markdown";

describe("SecretBadge", () => {
  it("renders secret masked by default and toggles visibility on click", () => {
    render(<SecretBadge name="TYPESAFE_API_KEY" env="production" value="sk-secret-12345" />);

    expect(screen.getByTestId("secret-name")).toHaveTextContent("TYPESAFE_API_KEY");
    expect(screen.getByTestId("secret-env")).toHaveTextContent("production");
    expect(screen.getByTestId("secret-value")).toHaveTextContent("••••••••••••••••");

    // Click toggle to reveal
    const toggleBtn = screen.getByTestId("secret-toggle");
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("secret-value")).toHaveTextContent("sk-secret-12345");

    // Click toggle to hide again
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("secret-value")).toHaveTextContent("••••••••••••••••");
  });

  it("copies secret to clipboard when copy button is clicked", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<SecretBadge name="DB_PASS" env="staging" value="superSecret99" />);
    const copyBtn = screen.getByTestId("secret-copy");
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith("superSecret99");
  });
});

describe("parseSecretSegments and Markdown secret rendering", () => {
  it("correctly identifies secret tags and markdown parts", () => {
    const content = 'Header text\n<secret name="API_KEY" env="production">secret_token_abc</secret>\nFooter text';
    const segments = parseSecretSegments(content);

    expect(segments).toHaveLength(3);
    expect(segments[0]).toEqual({ type: "markdown", text: "Header text\n" });
    expect(segments[1]).toEqual({
      type: "secret",
      name: "API_KEY",
      env: "production",
      value: "secret_token_abc",
    });
    expect(segments[2]).toEqual({ type: "markdown", text: "\nFooter text" });
  });

  it("renders SecretBadge inside Markdown when secret tag is present", () => {
    const content = 'Grave no ForgeVault:\n<secret name="TYPESAFE_KEY" env="production">ts_9999</secret>';
    render(<Markdown content={content} />);

    expect(screen.getByText("ForgeVault")).toBeInTheDocument();
    expect(screen.getByTestId("secret-name")).toHaveTextContent("TYPESAFE_KEY");
    expect(screen.getByTestId("secret-value")).toHaveTextContent("••••••••••••••••");
  });
});
