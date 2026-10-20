import { beforeEach, describe, expect, it } from "vitest";
import { getRememberMe, setRememberMe } from "./authStore";

describe("getRememberMe/setRememberMe", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to true when never set, so an existing session isn't logged out by this change", () => {
    expect(getRememberMe()).toBe(true);
  });

  it("persists an explicit false", () => {
    setRememberMe(false);
    expect(getRememberMe()).toBe(false);
  });

  it("persists an explicit true after a prior false", () => {
    setRememberMe(false);
    setRememberMe(true);
    expect(getRememberMe()).toBe(true);
  });
});
