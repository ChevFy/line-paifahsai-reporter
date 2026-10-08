import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import en from "../locales/en.json";
import th from "../locales/th.json";
import { LanguageProvider } from "../hooks/LanguageProvider";
import { AppError } from "../utils/app-error";
import ReportPage from "./ReportPage";

const { submitReport, uploadReportImage } = vi.hoisted(() => ({
  submitReport: vi.fn(),
  uploadReportImage: vi.fn(),
}));

vi.mock("../services/report-service", () => ({ submitReport, uploadReportImage }));

// Leaflet needs real layout; a stub that lets the test pick a location is enough here
vi.mock("../components/LocationMap", () => ({
  default: ({ onChange }: { onChange: (location: { latitude: number; longitude: number }) => void }) => (
    <button type="button" onClick={() => onChange({ latitude: 19.36, longitude: 98.44 })}>
      pick location
    </button>
  ),
}));

function renderPage() {
  return render(
    <LanguageProvider>
      <ReportPage />
    </LanguageProvider>,
  );
}

async function fillAndSubmit() {
  await userEvent.click(screen.getByRole("button", { name: "pick location" }));
  await userEvent.type(screen.getByRole("textbox"), "smoke near the river");
  await userEvent.click(screen.getByRole("button", { name: th.report.submit }));
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
});

describe("ReportPage errors follow the current language", () => {
  it("re-translates an image validation error after switching language", async () => {
    const { container } = renderPage();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;

    await userEvent.upload(input, new File(["x"], "a.gif", { type: "image/gif" }), {
      applyAccept: false,
    });
    expect(screen.getByText(th.errors.imageType)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: th.language.switchTo }));
    expect(screen.getByText(en.errors.imageType)).toBeInTheDocument();
    expect(screen.queryByText(th.errors.imageType)).not.toBeInTheDocument();
  });

  it("re-translates a client-side submit error after switching language", async () => {
    submitReport.mockRejectedValue(new AppError("network"));
    renderPage();

    await fillAndSubmit();
    expect(await screen.findByText(th.errors.network)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: th.language.switchTo }));
    expect(screen.getByText(en.errors.network)).toBeInTheDocument();
  });

  it("shows a backend message as-is", async () => {
    submitReport.mockRejectedValue(new Error("พิกัดอยู่นอกพื้นที่ให้บริการ"));
    renderPage();

    await fillAndSubmit();
    expect(await screen.findByText("พิกัดอยู่นอกพื้นที่ให้บริการ")).toBeInTheDocument();
  });

  it("shows the success screen with the report number", async () => {
    submitReport.mockResolvedValue({
      report_id: "R-123",
      message: "ok",
      emergency_phone: "1362",
    });
    renderPage();

    await fillAndSubmit();
    expect(await screen.findByText(th.success.title)).toBeInTheDocument();
    expect(screen.getByText(`${th.success.reportNumber} R-123`)).toBeInTheDocument();
  });
});
