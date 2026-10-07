import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { AlertCircle, Flame, MapPin } from "lucide-react";
import LocationMap from "../components/LocationMap";
import ImagePicker from "../components/ImagePicker";
import { submitReport, uploadReportImage } from "../services/report-service";
import type { ReportResponse } from "../types/report";
import { compressImage, validateImage } from "../utils/image";

type Location = { latitude: number; longitude: number };
const PAI_DISTRICT_CODE = "5803";

function createRequestId() {
  return crypto.randomUUID();
}

export default function ReportPage() {
  const [clientRequestId] = useState(createRequestId);
  const [location, setLocation] = useState<Location | null>(null);
  const [description, setDescription] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);

  const canSubmit = useMemo(
    () => Boolean(location && description.trim() && !isSubmitting),
    [description, isSubmitting, location],
  );

  function handleImageChange(file: File | null) {
    setImageError(file ? validateImage(file) : null);
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
          setImageError(reason instanceof Error ? reason.message : "อัปโหลดรูปไม่สำเร็จ");
        } finally {
          setIsUploadingImage(false);
        }
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ส่งรายงานไม่สำเร็จ");
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
      setImageError(reason instanceof Error ? reason.message : "อัปโหลดรูปไม่สำเร็จ");
    } finally {
      setIsUploadingImage(false);
    }
  }

  if (report) {
    return (
      <PageShell>
        <section className="success-card" role="status">
          <p className="eyebrow">ส่งข้อมูลแล้ว</p>
          <h2>ขอบคุณที่ช่วยแจ้งเหตุไฟป่า</h2>
          <p>{report.message}</p>
          <p className="emergency-notice">
            หากเป็นเหตุฉุกเฉิน โทร <strong>{report.emergency_phone || "1362"}</strong>
          </p>
          {image && (
            <div className="upload-retry">
              <p>แจ้งเหตุสำเร็จแล้ว แต่รูปยังไม่ได้อัปโหลด</p>
              {imageError && <p className="error-text">{imageError}</p>}
              <button type="button" onClick={handleImageUpload} disabled={isUploadingImage}>
                {isUploadingImage ? "กำลังอัปโหลดรูป..." : "ลองอัปโหลดรูปอีกครั้ง"}
              </button>
            </div>
          )}
          {!image && <p className="muted">หมายเลขรายงาน: {report.report_id}</p>}
        </section>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="emergency-banner">
        <p>หากพบเห็นไฟป่า กรุณาแจ้งเหตุทันที</p>
        <span>ข้อมูลจะถูกส่งให้เจ้าหน้าที่ดับเพลิงโดยทันที ไม่ต้องลงทะเบียน</span>
      </div>
      <form className="report-form" onSubmit={handleSubmit}>
        <fieldset disabled={isSubmitting}>
          <section className="form-section">
            <div className="section-heading">
              <MapPin size={16} />
              <span>ตำแหน่งเกิดเหตุ</span>
              <small>* จำเป็น</small>
            </div>
            <p className="district-scope">พื้นที่รับแจ้ง: อำเภอปาย จังหวัดแม่ฮ่องสอน</p>
            <p className="field-help">แตะบนแผนที่เพื่อปักหมุด หรือกดปุ่ม GPS เพื่อใช้ตำแหน่งปัจจุบัน</p>
            <LocationMap value={location} onChange={setLocation} />
          </section>
          {location && (
            <p className="coordinates">พิกัดที่เลือกเรียบร้อยแล้ว</p>
          )}

          <section className="form-section">
            <label>
              รายละเอียดเพิ่มเติม
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="เช่น เห็นควันจากบริเวณไหน มีบ้านหรือชุมชนใกล้เคียงหรือไม่"
                rows={4}
                required
              />
            </label>
          </section>
          <ImagePicker file={image} onChange={handleImageChange} disabled={isSubmitting} />
          {imageError && <p className="error-text">{imageError}</p>}
        </fieldset>

        {error && (
          <div className="error-box" role="alert">
            <AlertCircle size={16} />
            <p>{error}</p>
          </div>
        )}
        <button className="submit-button" type="submit" disabled={!canSubmit || Boolean(imageError)}>
          <Flame size={20} />
          {isSubmitting ? "กำลังส่งรายงาน..." : "ส่งรายงาน"}
        </button>
        <p className="form-note">ไม่ต้องสมัครสมาชิก ระบบจะยืนยันตัวตนผ่าน LINE</p>
      </form>
    </PageShell>
  );
}

function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="report-shell">
      <header className="report-header">
        <div className="report-header-inner">
          <div className="brand-icon" aria-hidden="true">
            <Flame size={20} />
          </div>
          <div>
            <h1>แจ้งเหตุไฟป่า</h1>
            <p>ระบบติดตามจุดความร้อน อ.ปาย</p>
          </div>
        </div>
      </header>
      <main className="report-page">{children}</main>
    </div>
  );
}
