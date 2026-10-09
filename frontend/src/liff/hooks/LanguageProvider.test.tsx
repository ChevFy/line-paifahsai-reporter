import { afterEach, describe, expect, it, vi } from "vitest";
import { render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LanguageSwitcher from "../components/LanguageSwitcher";
import en from "../locales/en.json";
import th from "../locales/th.json";
import { LanguageProvider } from "./LanguageProvider";
import { LANGUAGE_STORAGE_KEY } from "./language-storage";
import { useLanguage } from "./useLanguage";

function Title() {
  const { t } = useLanguage();
  return <h1>{t.header.title}</h1>;
}

function renderWithProvider() {
  return render(
    <LanguageProvider>
      <Title />
      <LanguageSwitcher />
    </LanguageProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LanguageProvider", () => {
  it("defaults to Thai for a Thai browser", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
    renderWithProvider();
    expect(screen.getByRole("heading")).toHaveTextContent(th.header.title);
    expect(document.documentElement.lang).toBe("th");
  });

  it("defaults to English for an English browser", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    renderWithProvider();
    expect(screen.getByRole("heading")).toHaveTextContent(en.header.title);
  });

  it("prefers the stored language over the browser language", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "th");
    renderWithProvider();
    expect(screen.getByRole("heading")).toHaveTextContent(th.header.title);
  });

  it("ignores an invalid stored value", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "fr");
    renderWithProvider();
    expect(screen.getByRole("heading")).toHaveTextContent(th.header.title);
  });

  it("switches language, updates <html lang> and remembers the choice", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
    const { unmount } = renderWithProvider();

    await userEvent.click(screen.getByRole("button", { name: th.language.switchTo }));

    expect(screen.getByRole("heading")).toHaveTextContent(en.header.title);
    expect(document.documentElement.lang).toBe("en");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");

    unmount();
    renderWithProvider();
    expect(screen.getByRole("heading")).toHaveTextContent(en.header.title);
  });

  it("still works when storage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
    renderWithProvider();

    await userEvent.click(screen.getByRole("button", { name: th.language.switchTo }));
    expect(screen.getByRole("heading")).toHaveTextContent(en.header.title);
  });
});

describe("useLanguage", () => {
  it("throws a clear error outside LanguageProvider", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderHook(() => useLanguage())).toThrow(
      "useLanguage must be used within LanguageProvider",
    );
  });
});
