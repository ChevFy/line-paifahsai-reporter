import {
  MAX_COMPRESSED_IMAGE_SIZE_BYTES,
  MAX_IMAGE_SIZE_BYTES,
} from "../config/api";
import { AppError } from "./app-error";
import type { ErrorCode } from "./app-error";

const SUPPORTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function validateImage(file: File): ErrorCode | null {
  if (!SUPPORTED_IMAGE_TYPES.has(file.type)) {
    return "imageType";
  }

  if (file.size > MAX_IMAGE_SIZE_BYTES) {
    return "imageSize";
  }

  return null;
}

export async function compressImage(file: File): Promise<File> {
  const image = await loadImage(file);
  const maxDimension = 1600;
  const scale = Math.min(1, maxDimension / Math.max(image.width, image.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.width * scale));
  canvas.height = Math.max(1, Math.round(image.height * scale));

  const context = canvas.getContext("2d");
  if (!context) {
    throw new AppError("imagePrepare");
  }

  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const blob = await canvasToBlob(canvas, file.type === "image/png" ? "image/png" : "image/jpeg");
  const compressedFile = new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), {
    type: blob.type,
  });

  if (compressedFile.size > MAX_COMPRESSED_IMAGE_SIZE_BYTES) {
    throw new AppError("imageTooLarge");
  }

  return compressedFile;
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new AppError("imageRead"));
    };
    image.src = objectUrl;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new AppError("imageCompress"))),
      type,
      0.82,
    );
  });
}
