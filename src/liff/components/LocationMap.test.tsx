import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import en from "../locales/en.json";
import th from "../locales/th.json";
import { LanguageProvider } from "../hooks/LanguageProvider";
import LanguageSwitcher from "./LanguageSwitcher";
import LocationMap from "./LocationMap";

function renderMap() {
  return render(
    <LanguageProvider>
      <LanguageSwitcher />
      <LocationMap value={null} onChange={() => undefined} />
    </LanguageProvider>,
  );
}

function mockGeolocationError(code: 1 | 2) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: (_success: PositionCallback, error: PositionErrorCallback) =>
        error({ code, PERMISSION_DENIED: 1 } as GeolocationPositionError),
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "geolocation");
});

describe("LocationMap", () => {
  it("re-translates a GPS permission error after switching language", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
    mockGeolocationError(1);
    renderMap();

    await userEvent.click(screen.getByRole("button", { name: th.location.useGps }));
    expect(screen.getByRole("alert")).toHaveTextContent(th.location.permissionDenied);

    await userEvent.click(screen.getByRole("button", { name: th.language.switchTo }));
    expect(screen.getByRole("alert")).toHaveTextContent(en.location.permissionDenied);
  });

  it("shows the unavailable message for other GPS errors", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    mockGeolocationError(2);
    renderMap();

    await userEvent.click(screen.getByRole("button", { name: en.location.useGps }));
    expect(screen.getByRole("alert")).toHaveTextContent(en.location.unavailable);
  });
});
