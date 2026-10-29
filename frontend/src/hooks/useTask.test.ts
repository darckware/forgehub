import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { taskUpdateErrorMessage } from "./useTask";

describe("taskUpdateErrorMessage", () => {
  it("shows the completion guard's code and message from a 409", () => {
    const error = new ApiError("Request to /api/v1/tasks/x failed with status 409", 409, {
      detail: { code: "COMPLETION_NO_EXECUTION", message: "Task cannot be completed: it has no execution" },
    });
    expect(taskUpdateErrorMessage(error)).toBe(
      "COMPLETION_NO_EXECUTION: Task cannot be completed: it has no execution",
    );
  });

  it("uses a plain string detail as is", () => {
    const error = new ApiError("failed", 409, { detail: "Task ready is set only by ActivateExecutionWave" });
    expect(taskUpdateErrorMessage(error)).toBe("Task ready is set only by ActivateExecutionWave");
  });

  it("falls back to the error message", () => {
    expect(taskUpdateErrorMessage(new Error("network down"))).toBe("network down");
    expect(taskUpdateErrorMessage(new ApiError("failed with 500", 500, undefined))).toBe("failed with 500");
  });
});
