import { api } from "./api";

export type Brand = {
  handle: string;
  colors: { bg?: string; primary?: string; accent?: string; text?: string };
  fonts: { heading?: string; body?: string; code?: string };
  /** The daily posting slots, "HH:MM" IST, sorted (brand/config.yaml post_times_ist). */
  post_times_ist?: string[];
};

const NUMBER_WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six"];

/** "Two slots a day." from the configured slot count; a neutral line when it is unknown. */
export function slotsHeadline(times: string[] | undefined): string {
  const n = times?.length ?? 0;
  if (!n) return "Every slot.";
  return n < NUMBER_WORDS.length ? `${NUMBER_WORDS[n]} slot${n === 1 ? "" : "s"} a day.` : `${n} slots a day.`;
}

/** Name a slot by the part of the day it falls in (IST). */
export function slotName(hhmm: string): string {
  const h = Number(hhmm.slice(0, 2));
  return h < 12 ? "Morning slot" : h < 17 ? "Afternoon slot" : "Evening slot";
}

const HEX = /^#[0-9a-f]{3,8}$/i;
const FONT = /^[\w\s-]{1,40}$/;

/** Load the brand from the API and apply it as CSS variables + Google Fonts. */
export async function applyBrand(): Promise<Brand | null> {
  let brand: Brand;
  try {
    brand = await api<Brand>("/api/public/brand");
  } catch {
    return null; // keep the CSS defaults (brand/config.yaml values)
  }
  const root = document.documentElement.style;
  const { colors = {}, fonts = {} } = brand;
  for (const [key, value] of Object.entries(colors)) {
    if (value && HEX.test(value)) root.setProperty(`--brand-${key}`, value);
  }
  const families: string[] = [];
  for (const [key, value] of Object.entries(fonts)) {
    if (!value || !FONT.test(value)) continue;
    root.setProperty(`--font-brand-${key}`, `'${value}'`);
    families.push(`family=${encodeURIComponent(value).replace(/%20/g, "+")}:wght@400;500;600;700;800`);
  }
  if (families.length) {
    const href = `https://fonts.googleapis.com/css2?${families.join("&")}&display=swap`;
    if (!document.querySelector(`link[href="${href}"]`)) {
      const link = Object.assign(document.createElement("link"), { rel: "stylesheet", href });
      document.head.appendChild(link);
    }
  }
  return brand;
}
