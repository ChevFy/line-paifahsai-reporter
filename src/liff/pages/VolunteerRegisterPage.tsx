import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import { AlertCircle, Loader2, UserPlus } from "lucide-react";
import liff from "../../liff";
import PageShell from "../components/PageShell";
import { PAI_DISTRICT_CODE } from "../config/api";
import { useLanguage } from "../hooks/useLanguage";
import { useMyVolunteer } from "../hooks/useMyVolunteer";
import { registerVolunteer } from "../services/volunteer-service";
import type { VolunteerRegistrationResponse } from "../types/volunteer";
import { formatError, toDisplayError } from "../utils/app-error";
import type { DisplayError, ErrorCode } from "../utils/app-error";
import { isValidThaiPhone, normalizeThaiPhone } from "../utils/phone";

const FULL_NAME_MAX_LENGTH = 200;

export default function VolunteerRegisterPage() {
  const { t } = useLanguage();
  const { state, reload, setRegistration } = useMyVolunteer();

  return (
    <PageShell title={t.volunteer.headerTitle} subtitle={t.volunteer.headerSubtitle}>
      {state.kind === "loading" && (
        <p className="loading-text" role="status">
          <Loader2 className="spin" size={16} />
          {t.volunteer.loading}
        </p>
      )}

      {state.kind === "error" && (
        <div className="error-box" role="alert">
          <AlertCircle size={16} />
          <div>
            <p>{formatError(state.error, t)}</p>
            <button type="button" className="inline-retry" onClick={reload}>
              {t.volunteer.retry}
            </button>
          </div>
        </div>
      )}

      {state.kind === "not-registered" && <RegistrationForm onRegistered={setRegistration} />}

      {state.kind === "registered" && <VolunteerStatusCard registration={state.registration} />}
    </PageShell>
  );
}

type FieldErrors = {
  fullName?: ErrorCode;
  phone?: ErrorCode;
};

function validateForm(fullName: string, phone: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!fullName) errors.fullName = "fullNameRequired";
  if (!isValidThaiPhone(phone)) errors.phone = "phoneInvalid";
  return errors;
}

function RegistrationForm({
  onRegistered,
}: {
  onRegistered: (registration: VolunteerRegistrationResponse) => void;
}) {
  const { t } = useLanguage();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [submitError, setSubmitError] = useState<DisplayError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;

    const trimmedName = fullName.trim();
    const normalizedPhone = normalizeThaiPhone(phone);
    const errors = validateForm(trimmedName, normalizedPhone);
    setFieldErrors(errors);
    setSubmitError(null);
    if (errors.fullName || errors.phone) return;

    setIsSubmitting(true);
    try {
      const registration = await registerVolunteer({
        full_name: trimmedName,
        phone: normalizedPhone,
        district_code: PAI_DISTRICT_CODE,
      });
      onRegistered(registration);
    } catch (reason) {
      setSubmitError(toDisplayError(reason, "registerVolunteer"));
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <div className="info-banner">
        <p>{t.volunteer.intro}</p>
        <span>{t.volunteer.scope}</span>
      </div>
      <form className="report-form" onSubmit={handleSubmit} noValidate>
        <fieldset disabled={isSubmitting}>
          <label htmlFor="volunteer-full-name">
            {t.volunteer.fullName}
            <input
              id="volunteer-full-name"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder={t.volunteer.fullNamePlaceholder}
              maxLength={FULL_NAME_MAX_LENGTH}
              aria-invalid={Boolean(fieldErrors.fullName)}
              aria-describedby={fieldErrors.fullName ? "volunteer-full-name-error" : undefined}
            />
          </label>
          {fieldErrors.fullName && (
            <p id="volunteer-full-name-error" className="error-text">
              {t.errors[fieldErrors.fullName]}
            </p>
          )}

          <label htmlFor="volunteer-phone">
            {t.volunteer.phone}
            <input
              id="volunteer-phone"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder={t.volunteer.phonePlaceholder}
              aria-invalid={Boolean(fieldErrors.phone)}
              aria-describedby={
                fieldErrors.phone ? "volunteer-phone-error" : "volunteer-phone-help"
              }
            />
          </label>
          {fieldErrors.phone ? (
            <p id="volunteer-phone-error" className="error-text">
              {t.errors[fieldErrors.phone]}
            </p>
          ) : (
            <p id="volunteer-phone-help" className="field-help">
              {t.volunteer.phoneHelp}
            </p>
          )}
        </fieldset>

        {submitError && (
          <div className="error-box" role="alert">
            <AlertCircle size={16} />
            <p>{formatError(submitError, t)}</p>
          </div>
        )}
        <button className="submit-button volunteer-submit" type="submit" disabled={isSubmitting}>
          <UserPlus size={20} />
          {isSubmitting ? t.volunteer.submitting : t.volunteer.submit}
        </button>
      </form>
    </>
  );
}

function VolunteerStatusCard({ registration }: { registration: VolunteerRegistrationResponse }) {
  const { t } = useLanguage();
  const { volunteer, created } = registration;
  const statusText = t.volunteer.status[volunteer.status];

  return (
    <section className="success-card" role="status">
      <p className={`status-badge status-${volunteer.status}`}>{statusText.label}</p>
      <h2>{statusText.title}</h2>
      <p>{statusText.description}</p>
      {!created && <p className="muted">{t.volunteer.alreadyRegistered}</p>}

      <dl className="volunteer-details">
        <dt>{t.volunteer.fullName}</dt>
        <dd>{volunteer.full_name}</dd>
        <dt>{t.volunteer.phone}</dt>
        <dd>{volunteer.phone}</dd>
      </dl>

      <div className="card-actions">
        <Link to="/" className="secondary-link">
          {t.volunteer.goToReport}
        </Link>
        {liff.isInClient() && (
          <button type="button" onClick={() => liff.closeWindow()}>
            {t.volunteer.close}
          </button>
        )}
      </div>
    </section>
  );
}
