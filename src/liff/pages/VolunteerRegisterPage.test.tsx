import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import en from "../locales/en.json";
import th from "../locales/th.json";
import { LanguageProvider } from "../hooks/LanguageProvider";
import type { VolunteerRegistrationResponse, VolunteerStatus } from "../types/volunteer";
import { AppError } from "../utils/app-error";
import VolunteerRegisterPage from "./VolunteerRegisterPage";

const { getMyVolunteer, registerVolunteer, isInClient, closeWindow } = vi.hoisted(() => ({
  getMyVolunteer: vi.fn(),
  registerVolunteer: vi.fn(),
  isInClient: vi.fn(),
  closeWindow: vi.fn(),
}));

vi.mock("../services/volunteer-service", () => ({ getMyVolunteer, registerVolunteer }));
vi.mock("../../liff", () => ({ default: { isInClient, closeWindow } }));

function makeRegistration(
  status: VolunteerStatus,
  created = true,
): VolunteerRegistrationResponse {
  return {
    volunteer: {
      id: 1,
      full_name: "สมชาย ใจดี",
      phone: "0812345678",
      district_code: "5803",
      status,
      approved_at: null,
      created_at: "2026-10-08T07:00:00Z",
    },
    created,
    message: "backend message",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <LanguageProvider>
        <VolunteerRegisterPage />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

async function fillForm(fullName: string, phone: string) {
  if (fullName) await userEvent.type(await screen.findByLabelText(th.volunteer.fullName), fullName);
  if (phone) await userEvent.type(screen.getByLabelText(th.volunteer.phone), phone);
}

function submitButton() {
  return screen.getByRole("button", { name: th.volunteer.submit });
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(navigator, "language", "get").mockReturnValue("th-TH");
  isInClient.mockReturnValue(false);
});

describe("VolunteerRegisterPage — loading the current status", () => {
  it("shows a loading state, then the form when not registered", async () => {
    getMyVolunteer.mockResolvedValue(null);
    renderPage();

    expect(screen.getByText(th.volunteer.loading)).toBeInTheDocument();
    expect(await screen.findByLabelText(th.volunteer.fullName)).toBeInTheDocument();
    expect(screen.getByText(th.volunteer.scope)).toBeInTheDocument();
  });

  it.each(["pending", "approved", "rejected", "suspended"] as const)(
    "shows the %s status instead of the form when already registered",
    async (status) => {
      getMyVolunteer.mockResolvedValue(makeRegistration(status, false));
      renderPage();

      expect(await screen.findByText(th.volunteer.status[status].title)).toBeInTheDocument();
      expect(screen.getByText(th.volunteer.status[status].label)).toBeInTheDocument();
      expect(screen.getByText(th.volunteer.alreadyRegistered)).toBeInTheDocument();
      expect(screen.queryByLabelText(th.volunteer.fullName)).not.toBeInTheDocument();
    },
  );

  it("shows a load error with retry, and recovers on retry", async () => {
    getMyVolunteer.mockRejectedValueOnce(new AppError("network")).mockResolvedValueOnce(null);
    renderPage();

    expect(await screen.findByText(th.errors.network)).toBeInTheDocument();
    expect(screen.queryByLabelText(th.volunteer.fullName)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: th.volunteer.retry }));
    expect(await screen.findByLabelText(th.volunteer.fullName)).toBeInTheDocument();
    expect(getMyVolunteer).toHaveBeenCalledTimes(2);
  });

  it("shows a backend auth error instead of the form", async () => {
    getMyVolunteer.mockRejectedValue(new Error("ยืนยันตัวตน LINE ไม่สำเร็จ กรุณาเปิดฟอร์มจาก LINE ใหม่"));
    renderPage();

    expect(
      await screen.findByText("ยืนยันตัวตน LINE ไม่สำเร็จ กรุณาเปิดฟอร์มจาก LINE ใหม่"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(th.volunteer.fullName)).not.toBeInTheDocument();
  });
});

describe("VolunteerRegisterPage — registration form", () => {
  beforeEach(() => {
    getMyVolunteer.mockResolvedValue(null);
  });

  it("validates required name and phone format without calling the API", async () => {
    renderPage();
    await fillForm("   ", "12345");
    await userEvent.click(submitButton());

    expect(screen.getByText(th.errors.fullNameRequired)).toBeInTheDocument();
    expect(screen.getByText(th.errors.phoneInvalid)).toBeInTheDocument();
    expect(screen.getByLabelText(th.volunteer.phone)).toHaveAttribute("aria-invalid", "true");
    expect(registerVolunteer).not.toHaveBeenCalled();
  });

  it("sends a trimmed name, normalized phone and the Pai district code", async () => {
    registerVolunteer.mockResolvedValue(makeRegistration("pending"));
    renderPage();
    await fillForm("  สมชาย ใจดี  ", "081-234-5678");
    await userEvent.click(submitButton());

    expect(registerVolunteer).toHaveBeenCalledWith({
      full_name: "สมชาย ใจดี",
      phone: "0812345678",
      district_code: "5803",
    });
    expect(await screen.findByText(th.volunteer.status.pending.title)).toBeInTheDocument();
    expect(screen.queryByText(th.volunteer.alreadyRegistered)).not.toBeInTheDocument();
    expect(screen.getByText("0812345678")).toBeInTheDocument();
  });

  it("submits only once while a request is in flight", async () => {
    let resolve: (value: VolunteerRegistrationResponse) => void = () => undefined;
    registerVolunteer.mockReturnValue(new Promise((done) => (resolve = done)));
    renderPage();
    await fillForm("สมชาย ใจดี", "0812345678");

    const form = submitButton().closest("form")!;
    await userEvent.click(submitButton());
    form.requestSubmit();
    form.requestSubmit();

    expect(screen.getByRole("button", { name: th.volunteer.submitting })).toBeDisabled();
    expect(screen.getByLabelText(th.volunteer.fullName)).toBeDisabled();
    expect(registerVolunteer).toHaveBeenCalledTimes(1);

    resolve(makeRegistration("pending"));
    expect(await screen.findByText(th.volunteer.status.pending.title)).toBeInTheDocument();
  });

  it("keeps the typed data and shows the backend error when registration fails", async () => {
    registerVolunteer.mockRejectedValueOnce(new Error("ไม่พบอำเภอที่เลือก กรุณาเลือกใหม่"));
    renderPage();
    await fillForm("สมชาย ใจดี", "0812345678");
    await userEvent.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("ไม่พบอำเภอที่เลือก กรุณาเลือกใหม่");
    expect(screen.getByLabelText(th.volunteer.fullName)).toHaveValue("สมชาย ใจดี");
    expect(screen.getByLabelText(th.volunteer.phone)).toHaveValue("0812345678");
    expect(submitButton()).toBeEnabled();

    registerVolunteer.mockResolvedValueOnce(makeRegistration("pending"));
    await userEvent.click(submitButton());
    expect(await screen.findByText(th.volunteer.status.pending.title)).toBeInTheDocument();
  });

  it("re-translates validation errors when switching language", async () => {
    renderPage();
    await screen.findByLabelText(th.volunteer.fullName);
    await userEvent.click(submitButton());
    expect(screen.getByText(th.errors.fullNameRequired)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: th.language.switchTo }));
    expect(screen.getByText(en.errors.fullNameRequired)).toBeInTheDocument();
    expect(screen.getByLabelText(en.volunteer.fullName)).toBeInTheDocument();
  });
});

describe("VolunteerRegisterPage — status card actions", () => {
  it("links back to the report page and hides close outside LINE", async () => {
    getMyVolunteer.mockResolvedValue(makeRegistration("approved", false));
    renderPage();

    const link = await screen.findByRole("link", { name: th.volunteer.goToReport });
    expect(link).toHaveAttribute("href", "/");
    expect(screen.queryByRole("button", { name: th.volunteer.close })).not.toBeInTheDocument();
  });

  it("closes the LIFF window inside LINE", async () => {
    isInClient.mockReturnValue(true);
    getMyVolunteer.mockResolvedValue(makeRegistration("approved", false));
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: th.volunteer.close }));
    expect(closeWindow).toHaveBeenCalledTimes(1);
  });
});
