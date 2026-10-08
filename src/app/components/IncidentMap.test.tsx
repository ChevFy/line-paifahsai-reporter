import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import L from "leaflet";
import type { ActiveIncident } from "../types/admin";
import { INCIDENT_STATUS_LABELS } from "../utils/incident-labels";
import IncidentMap from "./IncidentMap";

function makeIncident(overrides: Partial<ActiveIncident> = {}): ActiveIncident {
  return {
    id: 1,
    latitude: 19.36,
    longitude: 98.44,
    district_code: "5803",
    status: "open",
    report_count: 3,
    created_at: "2026-10-09T02:30:00Z",
    ...overrides,
  };
}

const first = makeIncident({ id: 1, latitude: 19.36, longitude: 98.44, report_count: 3 });
const second = makeIncident({ id: 2, latitude: 19.4, longitude: 98.5, status: "in_progress", report_count: 1 });

const marker = (id: number) => screen.getByTitle(new RegExp(`^เหตุ #${id} · `));
const pin = (id: number) => marker(id).querySelector(".incident-pin")!;

let fitBounds: ReturnType<typeof vi.spyOn>;
let panTo: ReturnType<typeof vi.spyOn>;
let remove: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  // jsdom has no layout (0×0 container), so the view-changing calls are spied and stubbed
  fitBounds = vi.spyOn(L.Map.prototype, "fitBounds").mockImplementation(function (this: L.Map) {
    return this;
  });
  panTo = vi.spyOn(L.Map.prototype, "panTo").mockImplementation(function (this: L.Map) {
    return this;
  });
  remove = vi.spyOn(L.Map.prototype, "remove");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("IncidentMap", () => {
  it("renders a labelled map with one marker per incident showing its report count and status", () => {
    render(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />);
    const region = screen.getByRole("region", { name: /^แผนที่เหตุที่กำลังเกิด/ });
    expect(region).toHaveClass("incident-map");
    expect(region).toHaveAccessibleName("แผนที่เหตุที่กำลังเกิด (ดูรายการเหตุทั้งหมดได้ที่รายการด้านข้าง)");
    expect(pin(1)).toHaveTextContent("3");
    expect(pin(1)).toHaveClass("incident-pin-open");
    expect(pin(2)).toHaveTextContent("1");
    expect(pin(2)).toHaveClass("incident-pin-in_progress");
    expect(pin(1)).not.toHaveClass("selected");
  });

  it("replaces markers when the incidents change", () => {
    const { rerender } = render(
      <IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />,
    );
    rerender(<IncidentMap fitKey="all" incidents={[second]} selectedId={null} onSelect={() => undefined} />);
    expect(screen.queryByTitle(/^เหตุ #1 · /)).not.toBeInTheDocument();
    expect(marker(2)).toBeInTheDocument();
    expect(document.querySelectorAll(".incident-pin")).toHaveLength(1);
  });

  it("clicking a marker calls the latest onSelect with the incident id", () => {
    const stale = vi.fn();
    const latest = vi.fn();
    const { rerender } = render(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={stale} />);
    rerender(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={latest} />);

    fireEvent.click(marker(2));
    expect(latest).toHaveBeenCalledWith(2);
    expect(stale).not.toHaveBeenCalled();
  });

  it("highlights the selected marker and pans to it only when the selection changes", () => {
    const { rerender } = render(
      <IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />,
    );
    expect(panTo).not.toHaveBeenCalled();

    rerender(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={2} onSelect={() => undefined} />);
    expect(pin(2)).toHaveClass("selected");
    expect(pin(1)).not.toHaveClass("selected");
    expect(panTo).toHaveBeenCalledTimes(1);
    expect(panTo).toHaveBeenCalledWith([19.4, 98.5]);

    // A refresh with the same selection must not yank the view back
    rerender(<IncidentMap fitKey="all" incidents={[{ ...first }, { ...second }]} selectedId={2} onSelect={() => undefined} />);
    expect(panTo).toHaveBeenCalledTimes(1);
    expect(pin(2)).toHaveClass("selected");
  });

  it("does not pan when the selected id is not among the incidents", () => {
    render(<IncidentMap fitKey="all" incidents={[first]} selectedId={99} onSelect={() => undefined} />);
    expect(panTo).not.toHaveBeenCalled();
  });

  it("fits the bounds once on the first non-empty list, not on later refreshes", () => {
    const { rerender } = render(<IncidentMap fitKey="all" incidents={[]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).not.toHaveBeenCalled();

    rerender(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(1);
    const bounds = fitBounds.mock.calls[0][0] as L.LatLngBounds;
    expect(bounds.getSouthWest()).toMatchObject({ lat: 19.36, lng: 98.44 });
    expect(bounds.getNorthEast()).toMatchObject({ lat: 19.4, lng: 98.5 });

    rerender(<IncidentMap fitKey="all" incidents={[second]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(1);
  });

  it("marker titles include the incident id and Thai status label", () => {
    render(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />);
    expect(screen.getByTitle(`เหตุ #1 · ${INCIDENT_STATUS_LABELS.open}`)).toBeInTheDocument();
    expect(screen.getByTitle(`เหตุ #2 · ${INCIDENT_STATUS_LABELS.in_progress}`)).toBeInTheDocument();
  });

  it("markers are not keyboard-focusable (the list is the keyboard path)", () => {
    render(<IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />);
    for (const id of [1, 2]) {
      expect(marker(id)).not.toHaveAttribute("tabindex");
      expect(marker(id)).not.toHaveAttribute("role", "button");
    }
  });

  it("re-fits the bounds once when fitKey changes, then not on later refreshes", () => {
    const { rerender } = render(
      <IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />,
    );
    expect(fitBounds).toHaveBeenCalledTimes(1);

    rerender(<IncidentMap fitKey="5803" incidents={[second]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(2);
    const bounds = fitBounds.mock.calls[1][0] as L.LatLngBounds;
    expect(bounds.getSouthWest()).toMatchObject({ lat: 19.4, lng: 98.5 });
    expect(bounds.getNorthEast()).toMatchObject({ lat: 19.4, lng: 98.5 });

    rerender(<IncidentMap fitKey="5803" incidents={[{ ...second }]} selectedId={null} onSelect={() => undefined} />);
    rerender(<IncidentMap fitKey="5803" incidents={[second]} selectedId={2} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(2);
  });

  it("after a fitKey change with an empty list (loading), fits once the new data arrives", () => {
    const { rerender } = render(
      <IncidentMap fitKey="all" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />,
    );
    expect(fitBounds).toHaveBeenCalledTimes(1);

    rerender(<IncidentMap fitKey="5801" incidents={[]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(1);

    rerender(<IncidentMap fitKey="5801" incidents={[first]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(2);

    rerender(<IncidentMap fitKey="5801" incidents={[first, second]} selectedId={null} onSelect={() => undefined} />);
    expect(fitBounds).toHaveBeenCalledTimes(2);
  });

  it("removes the Leaflet map on unmount", () => {
    const { unmount } = render(<IncidentMap fitKey="all" incidents={[first]} selectedId={null} onSelect={() => undefined} />);
    unmount();
    expect(remove).toHaveBeenCalledTimes(1);
  });
});
