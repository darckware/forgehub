import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { clearComposerStaging, nextPickerState, useChatComposerViewModel, type PickerState } from "./useChatComposerViewModel";

const closed: PickerState = { picker: null, query: "" };

describe("nextPickerState", () => {
  it("opens a picker only when its trigger starts a word", () => {
    expect(nextPickerState("ver @", closed)).toEqual({ picker: "file", query: "" });
    expect(nextPickerState("mail@", closed)).toEqual(closed);
    expect(nextPickerState("#", closed)).toEqual({ picker: "agent", query: "" });
    expect(nextPickerState("custa $", closed)).toEqual({ picker: "artifact", query: "" });
  });

  it("opens the slash picker only for a lone '/' and closes it once the text stops being a command", () => {
    expect(nextPickerState("/", closed)).toEqual({ picker: "slash", query: "" });
    expect(nextPickerState("a/", closed)).toEqual(closed);
    expect(nextPickerState("/de", { picker: "slash", query: "" })).toEqual({ picker: "slash", query: "" });
    expect(nextPickerState("", { picker: "slash", query: "" })).toEqual(closed);
  });

  it("tracks the query after # and $ and closes at the first space", () => {
    expect(nextPickerState("oi #Ath", { picker: "agent", query: "" })).toEqual({ picker: "agent", query: "Ath" });
    expect(nextPickerState("oi #Athos ", { picker: "agent", query: "Athos" })).toEqual(closed);
    expect(nextPickerState("oi", { picker: "agent", query: "" })).toEqual(closed);
    expect(nextPickerState("$doc", { picker: "artifact", query: "" })).toEqual({ picker: "artifact", query: "doc" });
  });

  it("keeps the file picker open while typing", () => {
    expect(nextPickerState("@src", { picker: "file", query: "" })).toEqual({ picker: "file", query: "" });
  });
});

describe("useChatComposerViewModel", () => {
  const file = (name: string) => new File(["x"], name, { type: "text/plain" });

  it("keeps a tab's draft and attachments across a remount, and forgets them once cleared", () => {
    const tabId = "tab-remount";
    const first = renderHook(() => useChatComposerViewModel(tabId, undefined, true));
    act(() => {
      first.result.current.changeText("rascunho");
      first.result.current.addFiles([file("a.txt")]);
    });
    first.unmount();

    const second = renderHook(() => useChatComposerViewModel(tabId, "seed ignorado", true));
    expect(second.result.current.text).toBe("rascunho");
    expect(second.result.current.files.map((f) => f.name)).toEqual(["a.txt"]);
    second.unmount();

    clearComposerStaging(tabId);
    const third = renderHook(() => useChatComposerViewModel(tabId, "seed", true));
    expect(third.result.current.text).toBe("seed");
    expect(third.result.current.files).toEqual([]);
  });

  it("takeDraft hands over text and files and leaves the composer empty", () => {
    const { result } = renderHook(() => useChatComposerViewModel("tab-send", undefined, true));
    act(() => {
      result.current.changeText("olá");
      result.current.addFiles([file("a.txt"), file("b.txt")]);
      result.current.setWarning("aviso antigo");
    });
    let draft: { text: string; files: File[] } | undefined;
    act(() => {
      draft = result.current.takeDraft();
    });
    expect(draft?.text).toBe("olá");
    expect(draft?.files.map((f) => f.name)).toEqual(["a.txt", "b.txt"]);
    expect(result.current.text).toBe("");
    expect(result.current.files).toEqual([]);
    expect(result.current.warning).toBeNull();
  });

  it("typing clears a stale warning", () => {
    const { result } = renderHook(() => useChatComposerViewModel("tab-warning", undefined, true));
    act(() => result.current.setWarning("digite algo"));
    act(() => result.current.changeText("a"));
    expect(result.current.warning).toBeNull();
  });

  it("the attach menu's triggers insert the character and open the matching picker", () => {
    const { result } = renderHook(() => useChatComposerViewModel("tab-trigger", undefined, true));
    act(() => result.current.changeText("ver"));
    act(() => result.current.insertTrigger("#"));
    expect(result.current.text).toBe("ver #");
    expect(result.current.picker).toBe("agent");

    act(() => result.current.insertTrigger("!"));
    expect(result.current.text).toBe("!ver #");
  });

  it("picking an agent or artifact replaces what was typed after the trigger", () => {
    const { result } = renderHook(() => useChatComposerViewModel("tab-pick", undefined, true));
    act(() => result.current.changeText("fala com #Ath"));
    act(() => result.current.selectAgentMention("Athos"));
    expect(result.current.text).toBe("fala com #Athos ");
    expect(result.current.picker).toBeNull();

    act(() => result.current.changeText("abre $rel"));
    act(() => result.current.selectArtifactMention("/docs/relatorio.md"));
    expect(result.current.text).toBe("abre /docs/relatorio.md ");

    act(() => result.current.changeText("veja @"));
    act(() => result.current.selectFileMention("/root/a.txt"));
    expect(result.current.text).toBe("veja /root/a.txt ");
  });

  it("removing the previewed image drops that attachment and closes the preview", () => {
    const { result } = renderHook(() => useChatComposerViewModel("tab-preview", undefined, true));
    act(() => result.current.addFiles([file("a.txt"), file("b.txt")]));
    act(() => result.current.openPreview(0));
    act(() => result.current.removePreviewed());
    expect(result.current.files.map((f) => f.name)).toEqual(["b.txt"]);
    expect(result.current.previewIndex).toBeNull();
    clearComposerStaging("tab-preview");
  });
});
