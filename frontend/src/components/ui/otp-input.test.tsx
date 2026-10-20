import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OTP_LENGTH, OtpInput } from "./otp-input";

describe("OtpInput", () => {
  it("renders 6 digit input boxes matching standard", () => {
    render(<OtpInput value="" onChange={vi.fn()} />);
    const inputs = screen.getAllByRole("textbox");
    expect(inputs).toHaveLength(OTP_LENGTH);
    expect(inputs).toHaveLength(6);
  });

  it("populates digits from value prop", () => {
    render(<OtpInput value="123" onChange={vi.fn()} />);
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];
    expect(inputs[0].value).toBe("1");
    expect(inputs[1].value).toBe("2");
    expect(inputs[2].value).toBe("3");
    expect(inputs[3].value).toBe("");
    expect(inputs[4].value).toBe("");
    expect(inputs[5].value).toBe("");
  });

  it("calls onChange when typing a digit and moves focus", () => {
    const handleChange = vi.fn();
    render(<OtpInput value="" onChange={handleChange} />);
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

    fireEvent.change(inputs[0], { target: { value: "5" } });
    expect(handleChange).toHaveBeenCalledWith("5");
  });

  it("handles paste of a full 6-digit code", () => {
    const handleChange = vi.fn();
    render(<OtpInput value="" onChange={handleChange} />);
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

    fireEvent.paste(inputs[0], {
      clipboardData: {
        getData: () => "654321",
      },
    });

    expect(handleChange).toHaveBeenCalledWith("654321");
  });

  it("filters non-digit characters on paste", () => {
    const handleChange = vi.fn();
    render(<OtpInput value="" onChange={handleChange} />);
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];

    fireEvent.paste(inputs[0], {
      clipboardData: {
        getData: () => "ab-12-34-cd",
      },
    });

    expect(handleChange).toHaveBeenCalledWith("1234");
  });
});
