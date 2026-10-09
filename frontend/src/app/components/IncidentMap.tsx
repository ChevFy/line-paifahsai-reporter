import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { ActiveIncident } from "../types/admin";
import { INCIDENT_STATUS_LABELS } from "../utils/incident-labels";

const PAI_CENTER: L.LatLngExpression = [19.358, 98.437];

type IncidentMapProps = {
  incidents: ActiveIncident[];
  fitKey: string;
  selectedId: number | null;
  onSelect: (incidentId: number) => void;
};

function incidentIcon(incident: ActiveIncident, isSelected: boolean) {
  const classes = ["incident-pin", `incident-pin-${incident.status}`];
  if (isSelected) classes.push("selected");
  return L.divIcon({
    className: "incident-marker",
    html: `<span class="${classes.join(" ")}">${incident.report_count}</span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

export default function IncidentMap({ incidents, fitKey, selectedId, onSelect }: IncidentMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const hasFittedRef = useRef(false);
  const onSelectRef = useRef(onSelect);

  // Read the latest values from refs so the pan effect below runs only when the selection changes
  const incidentsRef = useRef(incidents);

  useEffect(() => {
    onSelectRef.current = onSelect;
    incidentsRef.current = incidents;
  }, [onSelect, incidents]);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current).setView(PAI_CENTER, 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);

    return () => {
      mapRef.current = null;
      layerRef.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    hasFittedRef.current = false;
  }, [fitKey]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;

    layer.clearLayers();
    for (const incident of incidents) {
      L.marker([incident.latitude, incident.longitude], {
        icon: incidentIcon(incident, incident.id === selectedId),
        title: `เหตุ #${incident.id} · ${INCIDENT_STATUS_LABELS[incident.status]}`,
        // The list beside the map is the keyboard path; hundreds of focusable pins would trap Tab
        keyboard: false,
        zIndexOffset: incident.id === selectedId ? 1000 : 0,
      })
        .on("click", () => onSelectRef.current(incident.id))
        .addTo(layer);
    }

    // Fit once per filter so the 60-second refresh does not keep yanking the view away
    if (!hasFittedRef.current && incidents.length > 0) {
      const bounds = L.latLngBounds(incidents.map((incident) => [incident.latitude, incident.longitude]));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      hasFittedRef.current = true;
    }
  }, [incidents, selectedId]);

  // Pan only when the selection changes, not on every refresh
  useEffect(() => {
    const selected = incidentsRef.current.find((incident) => incident.id === selectedId);
    if (selected && mapRef.current) {
      mapRef.current.panTo([selected.latitude, selected.longitude]);
    }
  }, [selectedId]);

  return (
    <div
      className="incident-map"
      ref={containerRef}
      role="region"
      aria-label="แผนที่เหตุที่กำลังเกิด (ดูรายการเหตุทั้งหมดได้ที่รายการด้านข้าง)"
    />
  );
}
