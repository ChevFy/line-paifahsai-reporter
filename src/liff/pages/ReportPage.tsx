import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { AlertCircle, Flame, MapPin } from "lucide-react";
import LocationMap from "../components/LocationMap";
import ImagePicker from "../components/ImagePicker";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { submitReport, uploadReportImage } from "../services/report-service";
import type { ReportResponse } from "../types/report";
import { compressImage, validateImage } from "../utils/image";
import { formatError, toDisplayError } from "../utils/app-error";
import type { DisplayError } from "../utils/app-error";
import { useLanguage } from "../hooks/useLanguage";

type Location = { latitude: number; longitude: number };
const PAI_DISTRICT_CODE = "5803";

function createRequestId() {
  return crypto.randomUUID();
}

export default function ReportPage() {
  const { t } = useLanguage();
  const [clientRequestId] = useState(createRequestId);
  const [location, setLocation] = useState<Location | null>(null);
  const [description, setDescription] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<DisplayError | null>(null);
  const [imageError, setImageError] = useState<DisplayError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);

  const canSubmit = useMemo(
    () => Boolean(location && description.trim() && !isSubmitting),
    [description, isSubmitting, location],
  );

  function handleImageChange(file: File | null) {
    const code = file ? validateImage(file) : null;
    setImageError(code ? { code } : null);
    setImage(file);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!location || !description.trim() || isSubmitting) return;

    setError(null);
    setReport(null);
    setIsSubmitting(true);

    try {
      const response = await submitReport({
        client_request_id: clientRequestId,
        latitude: location.latitude,
        longitude: location.longitude,
        district_code: PAI_DISTRICT_CODE,
        description: description.trim(),
      });
      setReport(response);
      if (image && !imageError) {
        setIsUploadingImage(true);
        try {
          const compressedImage = await compressImage(image);
          await uploadReportImage(response.report_id, compressedImage);
          setImage(null);
        } catch (reason) {
          setImageError(toDisplayError(reason, "upload"));
        } finally {
          setIsUploadingImage(false);
        }
      }
    } catch (reason) {
      setError(toDisplayError(reason, "submit"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleImageUpload() {
    if (!report || !image || imageError || isUploadingImage) return;
    setIsUploadingImage(true);
    setImageError(null);

    try {
      const compressedImage = await compressImage(image);
      await uploadReportImage(report.report_id, compressedImage);
      setImage(null);
    } catch (reason) {
      setImageError(toDisplayError(reason, "upload"));
    } finally {
      setIsUploadingImage(false);
    }
  }

  if (report) {
    return (
      <PageShell>
        <section className="success-card" role="status">
          <p className="eyebrow">{t.success.eyebrow}</p>
          <h2>{t.success.title}</h2>
          <p>{report.message}</p>
          <p className="emergency-notice">
            {t.success.emergency} <strong>{report.emergency_phone || "1362"}</strong>
          </p>
          {image && (
            <div className="upload-retry">
              <p>{t.success.uploadFailed}</p>
              {imageError && <p className="error-text">{formatError(imageError, t)}</p>}
              <button type="button" onClick={handleImageUpload} disabled={isUploadingImage}>
                {isUploadingImage ? t.success.uploading : t.success.retryUpload}
              </button>
            </div>
          )}
          {!image && <p className="muted">{t.success.reportNumber} {report.report_id}</p>}
        </section>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="emergency-banner">
        <p>{t.alert.title}</p>
        <span>{t.alert.description}</span>
      </div>
      <form className="report-form" onSubmit={handleSubmit}>
        <fieldset disabled={isSubmitting}>
          <section className="form-section">
            <div className="section-heading">
              <MapPin size={16} />
              <span>{t.location.title}</span>
              <small>{t.location.required}</small>
            </div>
            <p className="district-scope">{t.location.scope}</p>
            <p className="field-help">{t.location.help}</p>
            <LocationMap value={location} onChange={setLocation} />
          </section>
          {location && (
            <p className="coordinates">{t.location.selected}</p>
          )}

          <section className="form-section">
            <label>
              {t.report.details}
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder={t.report.placeholder}
                rows={4}
                required
              />
            </label>
          </section>
          <ImagePicker file={image} onChange={handleImageChange} disabled={isSubmitting} />
          {imageError && <p className="error-text">{formatError(imageError, t)}</p>}
        </fieldset>

        {error && (
          <div className="error-box" role="alert">
            <AlertCircle size={16} />
            <p>{formatError(error, t)}</p>
          </div>
        )}
        <button className="submit-button" type="submit" disabled={!canSubmit || Boolean(imageError)}>
          <Flame size={20} />
          {isSubmitting ? t.report.submitting : t.report.submit}
        </button>
        <p className="form-note">{t.report.noRegistration}</p>
      </form>
    </PageShell>
  );
}

function PageShell({ children }: { children: ReactNode }) {
  const { t } = useLanguage();

  return (
    <div className="report-shell">
      <header className="report-header">
        <div className="report-header-inner">
          <div className="brand-icon" aria-hidden="true">
            <Flame size={20} />
          </div>
          <div>
            <h1>{t.header.title}</h1>
            <p>{t.header.subtitle}</p>
          </div>
          <LanguageSwitcher />
        </div>
      </header>
      <main className="report-page">{children}</main>
    </div>
  );
}
