import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConfirmDialog from "./ConfirmDialog";

function renderDialog(props: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      title="ระงับ สมชาย ใจดี?"
      description="สมชาย ใจดี จะไม่ได้รับแจ้งเหตุไฟป่า"
      confirmLabel="ระงับ"
      isBusy={false}
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...props}
    />,
  );
  return { onConfirm, onCancel };
}

afterEach(() => {
  // Unmount before resetting mocks so no effect runs against reset (undefined) mocks
  cleanup();
  vi.resetAllMocks();
});

describe("ConfirmDialog", () => {
  it("is an accessible alertdialog labelled by its title and description", () => {
    renderDialog();
    const dialog = screen.getByRole("alertdialog", { name: "ระงับ สมชาย ใจดี?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("สมชาย ใจดี จะไม่ได้รับแจ้งเหตุไฟป่า");
  });

  it("focuses the cancel button first so a stray Enter does not confirm", async () => {
    const { onConfirm, onCancel } = renderDialog();
    expect(screen.getByRole("button", { name: "ยกเลิก" })).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onConfirm / onCancel on click", async () => {
    const { onConfirm, onCancel } = renderDialog();
    await userEvent.click(screen.getByRole("button", { name: "ระงับ" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "ยกเลิก" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", async () => {
    const { onCancel } = renderDialog();
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("while busy: buttons disabled, busy label shown, Escape ignored", async () => {
    const { onCancel } = renderDialog({ isBusy: true });
    expect(screen.getByRole("button", { name: "ยกเลิก" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "กำลังดำเนินการ..." })).toBeDisabled();

    await userEvent.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });
});
