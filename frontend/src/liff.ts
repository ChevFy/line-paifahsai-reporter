import liff from "@line/liff";

let initPromise: Promise<void> | null = null;

export function initLiff() {
  if (!initPromise) {
    initPromise = liff.init({ liffId: import.meta.env.VITE_LIFF_ID });
  }
  return initPromise;
}

export default liff;