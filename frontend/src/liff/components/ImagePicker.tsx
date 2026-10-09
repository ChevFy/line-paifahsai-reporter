import { useEffect, useMemo } from "react";
import { Camera, ImageIcon, X } from "lucide-react";
import { useLanguage } from "../hooks/useLanguage";

type ImagePickerProps = {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
};

export default function ImagePicker({ file, onChange, disabled }: ImagePickerProps) {
  const { t } = useLanguage();
  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  return (
    <div className="image-picker">
      <div className="section-heading">
        <Camera size={16} />
        <span>{t.image.title}</span>
        <small>{t.image.optional}</small>
      </div>
      {previewUrl ? (
        <div className="image-preview">
          <img src={previewUrl} alt={t.image.preview} />
          <button
            type="button"
            className="remove-image-button"
            onClick={() => onChange(null)}
            disabled={disabled}
            aria-label={t.image.remove}
          >
            <X size={14} />
          </button>
        </div>
      ) : (
        <label className="image-dropzone">
          <Camera size={30} />
          <span>{t.image.choose}</span>
          <small>{t.image.hint}</small>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            disabled={disabled}
            onChange={(event) => onChange(event.target.files?.[0] ?? null)}
          />
        </label>
      )}
      {file && <p className="selected-file"><ImageIcon size={14} />{file.name}</p>}
    </div>
  );
}
