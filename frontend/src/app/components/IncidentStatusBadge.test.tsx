import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { IncidentStatus } from "../types/admin";
import { INCIDENT_STATUS_LABELS } from "../utils/incident-labels";
import IncidentStatusBadge from "./IncidentStatusBadge";

afterEach(cleanup);

describe("IncidentStatusBadge", () => {
  it.each<IncidentStatus>(["open", "in_progress"])(
    "renders the Thai label for %s with the shared status classes",
    (status) => {
      render(<IncidentStatusBadge status={status} />);
      const badge = screen.getByText(INCIDENT_STATUS_LABELS[status]);
      expect(badge.tagName).toBe("SPAN");
      expect(badge).toHaveClass("status-badge", `status-${status}`);
    },
  );
});
