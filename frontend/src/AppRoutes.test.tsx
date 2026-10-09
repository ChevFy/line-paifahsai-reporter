import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import th from "./liff/locales/th.json";
import { LanguageProvider } from "./liff/hooks/LanguageProvider";
import { AppRoutes } from "./App";

vi.mock("./liff", () => ({
  default: { isInClient: () => false },
  initLiff: vi.fn(),
}));
vi.mock("./liff/services/volunteer-service", () => ({
  getMyVolunteer: vi.fn().mockResolvedValue(null),
  registerVolunteer: vi.fn(),
}));
vi.mock("./liff/components/LocationMap", () => ({ default: () => null }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LanguageProvider>
        <AppRoutes />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
});

describe("AppRoutes", () => {
  it("renders the report page at /", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { name: th.header.title })).toBeInTheDocument();
  });

  it("renders the volunteer registration page at /register", async () => {
    renderAt("/register");
    expect(screen.getByRole("heading", { name: th.volunteer.headerTitle })).toBeInTheDocument();
    expect(await screen.findByLabelText(th.volunteer.fullName)).toBeInTheDocument();
  });

  it("redirects unknown paths to the report page", () => {
    renderAt("/nope");
    expect(screen.getByRole("heading", { name: th.header.title })).toBeInTheDocument();
  });
});
