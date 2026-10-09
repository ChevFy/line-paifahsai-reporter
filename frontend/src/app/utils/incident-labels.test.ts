import { describe, expect, it } from "vitest";
import { INCIDENT_STATUS_LABELS } from "./incident-labels";

describe("INCIDENT_STATUS_LABELS", () => {
  it("has a Thai label for every active status", () => {
    expect(INCIDENT_STATUS_LABELS).toEqual({
      open: "ยังไม่มีคนรับ",
      in_progress: "มีจิตอาสารับแล้ว",
    });
  });
});
