/**
 * The legal entity behind Mintly, shown on the legal pages (/legal/*), and later on invoices and footers.
 * Fill in every null before taking real payments: while any is missing, the legal pages show a Draft notice
 * (docs/legal/compliance.md lists what each field is for).
 */
export const COMPANY = {
  product: "Mintly",
  legalName: "Anjanex Labs",
  entityType: null as string | null,          // e.g. "a sole proprietorship" or "a private limited company"
  address: null as string | null,             // registered address, as on GST / incorporation papers
  email: null as string | null,               // monitored support and grievance inbox
  phone: null as string | null,
  grievanceOfficer: null as string | null,    // name of the grievance officer (E-Commerce Rules 2020)
  courtsCity: null as string | null,          // city whose courts hear disputes, e.g. "Mumbai"
  gstin: null as string | null,               // once GST-registered
};

export const POLICY_UPDATED = "22 October 2026";

/** Fields still to fill in; non-empty means the policies are drafts. */
export const MISSING: string[] = Object.entries(COMPANY)
  .filter(([key, value]) => value === null && key !== "gstin")
  .map(([key]) => key);

const LABEL: Record<string, string> = {
  entityType: "type of business", address: "registered address", email: "contact email", phone: "phone number",
  grievanceOfficer: "grievance officer", courtsCity: "city for disputes",
};

/** A company field for running text: its value, or a visible "[… to be added]" while it's missing. */
export function field(key: keyof typeof COMPANY): string {
  return COMPANY[key] ?? `[${LABEL[key] ?? key} to be added]`;
}
