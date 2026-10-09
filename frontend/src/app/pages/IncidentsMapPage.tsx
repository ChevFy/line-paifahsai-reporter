import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { AlertCircle, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import IncidentMap from "../components/IncidentMap";
import IncidentStatusBadge from "../components/IncidentStatusBadge";
import { useActiveIncidents } from "../hooks/useActiveIncidents";
import { useDistricts } from "../hooks/useDistricts";
import type { ActiveIncident } from "../types/admin";
import { formatDateTime, formatElapsed, formatTime } from "../utils/format";

const EMERGENCY_PHONE_FALLBACK = "1362";

// Incidents nobody has accepted yet come first; the backend already returns newest
// first and Array.sort is stable, so that order is kept within each status
function sortByUrgency(incidents: ActiveIncident[]): ActiveIncident[] {
  return [...incidents].sort((a, b) => {
    if (a.status === b.status) return 0;
    return a.status === "open" ? -1 : 1;
  });
}

function googleMapsUrl(incident: ActiveIncident): string {
  return `https://www.google.com/maps/search/?api=1&query=${incident.latitude.toFixed(6)},${incident.longitude.toFixed(6)}`;
}

export default function IncidentsMapPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const districtCode = searchParams.get("district") || null;
  const { districts, error: districtError } = useDistricts();
  const { data, serverNow, error, isLoading, reload } = useActiveIncidents(districtCode);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    if (selectedId === null) return;
    document.getElementById(`incident-${selectedId}`)?.scrollIntoView?.({ block: "nearest" });
  }, [selectedId]);

  const incidents = data ? sortByUrgency(data.incidents) : [];
  const openCount = incidents.filter((incident) => incident.status === "open").length;
  const districtNames = new Map(districts.map((district) => [district.code, district.name_th]));

  function changeDistrict(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set("district", value);
    else next.delete("district");
    setSearchParams(next);
    setSelectedId(null);
  }

  return (
    <section className="admin-panel" aria-labelledby="incidents-title">
      <div className="panel-header">
        <div>
          <h2 id="incidents-title">เหตุที่กำลังเกิด</h2>
          <p className="muted">
            {data
              ? `${incidents.length} เหตุ · ยังไม่มีคนรับ ${openCount} เหตุ · อัปเดตล่าสุด ${formatTime(data.generated_at)} น.`
              : isLoading
                ? "กำลังโหลด..."
                : null}
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={reload} disabled={isLoading}>
          <RefreshCw size={16} />
          โหลดใหม่
        </button>
      </div>

      <div className="filter-bar">
        <p className="muted">
          หน้านี้อัปเดตเองทุก 1 นาที · เหตุด่วนโทร{" "}
          <strong>{data?.emergency_phone ?? EMERGENCY_PHONE_FALLBACK}</strong>
        </p>
        <label className="district-filter">
          อำเภอ
          <select value={districtCode ?? ""} onChange={(event) => changeDistrict(event.target.value)}>
            <option value="">ทุกอำเภอ</option>
            {districts.map((district) => (
              <option key={district.code} value={district.code}>
                {district.name_th}
              </option>
            ))}
          </select>
        </label>
      </div>

      {districtError && (
        <div className="error-box" role="alert">
          <AlertCircle size={16} />
          <p>{districtError}</p>
        </div>
      )}

      {error && (
        <div className="error-box" role="alert">
          <AlertCircle size={16} />
          <p>
            {error}
            {data && " · ข้อมูลบนแผนที่อาจไม่เป็นปัจจุบัน"}
          </p>
          <button type="button" className="secondary-button" onClick={reload}>
            ลองอีกครั้ง
          </button>
        </div>
      )}

      {data?.truncated && (
        <div className="notice-box" role="status">
          <AlertCircle size={16} />
          <p>มีเหตุมากเกินกว่าจะแสดงทั้งหมด แสดงเฉพาะ {incidents.length} เหตุล่าสุด กรองตามอำเภอเพื่อดูให้ครบ</p>
        </div>
      )}

      <div className="incidents-layout">
        <IncidentMap
          incidents={incidents}
          fitKey={districtCode ?? "all"}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />

        <div className="incident-list" aria-busy={isLoading}>
          {!data && isLoading && (
            <p className="loading-text" role="status">
              <Loader2 className="spin" size={16} />
              กำลังโหลดเหตุที่กำลังเกิด...
            </p>
          )}
          {data && incidents.length === 0 && (
            <p className="empty-state">ไม่มีเหตุที่กำลังเกิดอยู่ตอนนี้</p>
          )}
          <ul>
            {incidents.map((incident) => (
              <li key={incident.id} id={`incident-${incident.id}`}>
                <button
                  type="button"
                  className={incident.id === selectedId ? "incident-item selected" : "incident-item"}
                  aria-pressed={incident.id === selectedId}
                  onClick={() => setSelectedId(incident.id)}
                >
                  <span className="incident-item-head">
                    <strong>เหตุ #{incident.id}</strong>
                    <IncidentStatusBadge status={incident.status} />
                  </span>
                  <span>
                    อ.{districtNames.get(incident.district_code) ?? incident.district_code} · แจ้ง{" "}
                    {incident.report_count} ครั้ง
                  </span>
                  <span className="muted">
                    {serverNow && formatElapsed(incident.created_at, serverNow)} ·{" "}
                    {formatDateTime(incident.created_at)}
                  </span>
                </button>
                <a
                  className="incident-map-link"
                  href={googleMapsUrl(incident)}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`เปิดเหตุ #${incident.id} ใน Google Maps`}
                >
                  <ExternalLink size={16} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
