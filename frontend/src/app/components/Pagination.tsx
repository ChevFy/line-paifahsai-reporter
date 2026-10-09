type PaginationProps = {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
  disabled?: boolean;
};

export default function Pagination({ page, pageCount, onChange, disabled }: PaginationProps) {
  if (pageCount <= 1) return null;

  return (
    <nav className="pagination" aria-label="เลือกหน้า">
      <button
        type="button"
        className="secondary-button"
        onClick={() => onChange(page - 1)}
        disabled={disabled || page <= 1}
      >
        ก่อนหน้า
      </button>
      <span aria-current="page">
        หน้า {page} / {pageCount}
      </span>
      <button
        type="button"
        className="secondary-button"
        onClick={() => onChange(page + 1)}
        disabled={disabled || page >= pageCount}
      >
        ถัดไป
      </button>
    </nav>
  );
}
