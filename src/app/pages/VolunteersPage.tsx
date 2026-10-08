import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import ConfirmDialog from "../components/ConfirmDialog";
import Pagination from "../components/Pagination";
import StatusBadge from "../components/StatusBadge";
import { useDistricts } from "../hooks/useDistricts";
import { useVolunteerPage } from "../hooks/useVolunteerPage";
import { changeVolunteerStatus } from "../services/volunteer-service";
import type { Volunteer, VolunteerAction, VolunteerStatus } from "../types/admin";
import { ApiError, errorMessage } from "../utils/api-error";
import { formatDateTime } from "../utils/format";
import { STATUS_LABELS } from "../utils/volunteer-labels";

export const PAGE_SIZE = 50;

const STATUS_TABS: Array<{ value: VolunteerStatus | "all"; label: string }> = [
  { value: "pending", label: STATUS_LABELS.pending },
  { value: "approved", label: STATUS_LABELS.approved },
  { value: "rejected", label: STATUS_LABELS.rejected },
  { value: "suspended", label: STATUS_LABELS.suspended },
  { value: "all", label: "ทั้งหมด" },
];

const ACTIONS_BY_STATUS: Record<VolunteerStatus, VolunteerAction[]> = {
  pending: ["approve", "reject"],
  approved: ["suspend"],
  rejected: ["approve"],
  suspended: ["approve"],
};

const ACTION_LABELS: Record<VolunteerAction, string> = {
  approve: "อนุมัติ",
  reject: "ไม่อนุมัติ",
  suspend: "ระงับ",
};

// Actions that stop someone from receiving fire alerts need an explicit confirmation
const CONFIRM_TEXT: Partial<Record<VolunteerAction, (name: string) => string>> = {
  reject: (name) => `${name} จะไม่ได้เป็นจิตอาสาและจะได้รับแจ้งผลทาง LINE`,
  suspend: (name) =>
    `${name} จะไม่ได้รับแจ้งเหตุไฟป่าอีกจนกว่าจะอนุมัติใหม่ และจะได้รับแจ้งผลทาง LINE`,
};

function isVolunteerStatus(value: string): value is VolunteerStatus {
  return Object.hasOwn(STATUS_LABELS, value);
}

function readStatus(value: string | null): VolunteerStatus | null {
  if (value === "all") return null;
  if (value && isVolunteerStatus(value)) return value;
  return "pending";
}

function readPage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page >= 1 ? page : 1;
}

type PendingAction = { volunteer: Volunteer; action: VolunteerAction };
type Notice = { kind: "success" | "error"; message: string };

export default function VolunteersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = readStatus(searchParams.get("status"));
  const districtCode = searchParams.get("district") || null;
  const currentPage = readPage(searchParams.get("page"));

  const { districts, error: districtError } = useDistricts();
  const { page, error, isLoading, reload } = useVolunteerPage({
    status,
    districtCode,
    limit: PAGE_SIZE,
    offset: (currentPage - 1) * PAGE_SIZE,
  });

  const [confirming, setConfirming] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState<PendingAction | null>(null);
  // State updates are async; the ref blocks a second action fired before the re-render
  const isActionRunning = useRef(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const pageCount = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const districtNames = new Map(districts.map((district) => [district.code, district.name_th]));

  function updateParams(changes: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setSearchParams(next);
  }

  // After the last row of the last page is handled, step back to a page that has rows
  const isPastLastPage =
    !isLoading && page !== null && page.items.length === 0 && page.total > 0 && currentPage > pageCount;
  useEffect(() => {
    if (!isPastLastPage) return;
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("page", String(pageCount));
        return next;
      },
      { replace: true },
    );
  }, [isPastLastPage, pageCount, setSearchParams]);

  function requestAction(volunteer: Volunteer, action: VolunteerAction) {
    if (CONFIRM_TEXT[action]) {
      setConfirming({ volunteer, action });
      return;
    }
    void runAction({ volunteer, action });
  }

  async function runAction({ volunteer, action }: PendingAction) {
    if (isActionRunning.current) return;
    isActionRunning.current = true;
    setBusy({ volunteer, action });
    setNotice(null);
    try {
      await changeVolunteerStatus(volunteer.id, action);
      setNotice({
        kind: "success",
        message: `${ACTION_LABELS[action]} ${volunteer.full_name} แล้ว`,
      });
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) return;
      setNotice({ kind: "error", message: errorMessage(reason, "เปลี่ยนสถานะจิตอาสาไม่สำเร็จ") });
    } finally {
      isActionRunning.current = false;
      setBusy(null);
      setConfirming(null);
      // Reload instead of removing the row locally: the offset would shift otherwise
      reload();
    }
  }

  return (
    <section className="admin-panel" aria-labelledby="volunteers-title">
      <div className="panel-header">
        <div>
          <h2 id="volunteers-title">จิตอาสา</h2>
          <p className="muted">
            {page
              ? `ทั้งหมด ${page.total.toLocaleString("th-TH")} คน`
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
        <div className="status-tabs" role="group" aria-label="กรองตามสถานะ">
          {STATUS_TABS.map((tab) => {
            const isActive = (status ?? "all") === tab.value;
            return (
              <button
                key={tab.value}
                type="button"
                className={isActive ? "tab active" : "tab"}
                aria-pressed={isActive}
                onClick={() => updateParams({ status: tab.value, page: null })}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
        <label className="district-filter">
          อำเภอ
          <select
            value={districtCode ?? ""}
            onChange={(event) => updateParams({ district: event.target.value || null, page: null })}
          >
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

      {notice && (
        <div
          className={notice.kind === "success" ? "success-box" : "error-box"}
          role={notice.kind === "success" ? "status" : "alert"}
        >
          {notice.kind === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <p>{notice.message}</p>
        </div>
      )}

      {error && (
        <div className="error-box" role="alert">
          <AlertCircle size={16} />
          <p>{error}</p>
          <button type="button" className="secondary-button" onClick={reload}>
            ลองอีกครั้ง
          </button>
        </div>
      )}

      <div className="table-wrap" aria-busy={isLoading}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">ชื่อ-นามสกุล</th>
              <th scope="col">เบอร์โทร</th>
              <th scope="col">อำเภอ</th>
              <th scope="col">สถานะ</th>
              <th scope="col">สมัครเมื่อ</th>
              <th scope="col">อนุมัติเมื่อ</th>
              <th scope="col">
                <span className="visually-hidden">การจัดการ</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {page?.items.map((volunteer) => (
              <tr key={volunteer.id}>
                <td>{volunteer.full_name}</td>
                <td>
                  <a href={`tel:${volunteer.phone}`}>{volunteer.phone}</a>
                </td>
                <td>{districtNames.get(volunteer.district_code) ?? volunteer.district_code}</td>
                <td>
                  <StatusBadge status={volunteer.status} />
                </td>
                <td>{formatDateTime(volunteer.created_at)}</td>
                <td>{formatDateTime(volunteer.approved_at)}</td>
                <td>
                  <div className="row-actions">
                    {ACTIONS_BY_STATUS[volunteer.status].map((action) => (
                      <button
                        key={action}
                        type="button"
                        className={action === "approve" ? "primary-button" : "danger-outline-button"}
                        onClick={() => requestAction(volunteer, action)}
                        disabled={busy !== null || confirming !== null || isLoading}
                        aria-label={`${ACTION_LABELS[action]} ${volunteer.full_name}`}
                      >
                        {busy?.volunteer.id === volunteer.id && busy.action === action && (
                          <Loader2 className="spin" size={16} />
                        )}
                        {ACTION_LABELS[action]}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {page && page.items.length === 0 && !isLoading && (
          <p className="empty-state">ไม่มีจิตอาสาในหมวดนี้</p>
        )}
        {!page && isLoading && (
          <p className="loading-text" role="status">
            <Loader2 className="spin" size={16} />
            กำลังโหลดรายชื่อจิตอาสา...
          </p>
        )}
      </div>

      <Pagination
        page={currentPage}
        pageCount={pageCount}
        disabled={isLoading}
        onChange={(next) => updateParams({ page: next === 1 ? null : String(next) })}
      />

      {confirming && (
        <ConfirmDialog
          title={`${ACTION_LABELS[confirming.action]} ${confirming.volunteer.full_name}?`}
          description={CONFIRM_TEXT[confirming.action]?.(confirming.volunteer.full_name) ?? ""}
          confirmLabel={ACTION_LABELS[confirming.action]}
          isBusy={busy !== null}
          onConfirm={() => void runAction(confirming)}
          onCancel={() => setConfirming(null)}
        />
      )}
    </section>
  );
}
