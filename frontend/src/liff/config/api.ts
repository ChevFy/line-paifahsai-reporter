const configuredBackendApi =
  import.meta.env.VITE_BACKEND_API ?? import.meta.env.VITE_API_BASE_URL;

export const API_BASE_URL = (configuredBackendApi ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024;
export const MAX_COMPRESSED_IMAGE_SIZE_BYTES = 5 * 1024 * 1024;

// The service covers Pai District, Mae Hong Son only
export const PAI_DISTRICT_CODE = "5803";
