const THAI_PHONE_PATTERN = /^0[0-9]{8,9}$/;

// Accepts what people usually type ("081-234-5678", "+66 81 234 5678")
// and returns the digits-only form the backend expects
export function normalizeThaiPhone(input: string): string {
  const digits = input.replace(/[\s()-]/g, "");
  if (digits.startsWith("+66")) return `0${digits.slice(3)}`;
  return digits;
}

export function isValidThaiPhone(phone: string): boolean {
  return THAI_PHONE_PATTERN.test(phone);
}
