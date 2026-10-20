import { afterEach, expect, it } from "vitest";
import i18n, { UI_LANGUAGE_STORAGE_KEY } from "./index";

afterEach(async () => {
  await i18n.changeLanguage("pt-BR");
});

it("keeps the document language and saved preference in sync", async () => {
  await i18n.changeLanguage("es");
  expect(document.documentElement.lang).toBe("es");
  expect(localStorage.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe("es");

  await i18n.changeLanguage("en");
  expect(document.documentElement.lang).toBe("en");
});
