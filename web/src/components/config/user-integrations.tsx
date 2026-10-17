/**
 * Per-user integration settings: Telegram chat ID, Instagram, YouTube credentials.
 * Calls /api/integrations (PUT per key, GET for status).
 */
import { useCallback, useEffect, useState } from "react";
import { Check, CircleDashed } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

type KeyStatus = { set: boolean; masked: string | null };
type ValuesResponse = { values: Record<string, KeyStatus> };

async function getIntegrations(): Promise<ValuesResponse> {
  return api<ValuesResponse>("/api/integrations");
}

async function putIntegration(key: string, value: string): Promise<void> {
  await api(`/api/integrations/${key}`, { method: "PUT", body: { value } });
}

// ------------------------------------------------------------------------------------------------
// One section (e.g. Instagram) with a set of fields and a single Save button
// ------------------------------------------------------------------------------------------------
type SectionField = { key: string; label: string; secret: boolean; placeholder: string };

function IntegrationSection({
  title,
  fields,
  statuses,
  onSaved,
}: {
  title: string;
  fields: SectionField[];
  statuses: Record<string, KeyStatus>;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const toSave = Object.entries(values).filter(([, v]) => v.trim().length > 0);
    if (!toSave.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const [key, value] of toSave) {
        await putIntegration(key, value.trim());
      }
      setValues({});
      onSaved();
      toast.success(`${title} saved`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const dirty = fields.some((f) => (values[f.key] ?? "").trim().length > 0);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {fields.map((f) => {
          const st = statuses[f.key];
          return (
            <div key={f.key} className="grid gap-1.5">
              <div className="flex items-center gap-2">
                <Label htmlFor={`ucf-${f.key}`} className="text-sm font-medium">
                  {f.label}
                </Label>
                {st?.set ? (
                  <span className="inline-flex items-center gap-1 text-xs text-ok">
                    <Check className="size-3" aria-hidden />
                    Set{st.masked ? ` · ${st.masked}` : ""}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <CircleDashed className="size-3" aria-hidden />
                    Not set
                  </span>
                )}
              </div>
              <Input
                id={`ucf-${f.key}`}
                type={f.secret ? "password" : "text"}
                placeholder={st?.set ? "Enter a new value to replace" : f.placeholder}
                value={values[f.key] ?? ""}
                onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                disabled={busy}
                autoComplete="off"
                spellCheck={false}
                autoCapitalize="none"
                data-1p-ignore
                data-lpignore="true"
                className="font-mono text-sm"
              />
            </div>
          );
        })}
        {error && <p className="text-xs text-bad">{error}</p>}
        <Button size="sm" onClick={handleSave} disabled={busy || !dirty} className="w-fit">
          {busy ? "Saving…" : `Save ${title}`}
        </Button>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------
// Full component
// ------------------------------------------------------------------------------------------------
const TELEGRAM_FIELDS: SectionField[] = [
  { key: "TG_CHAT_ID", label: "Chat ID", secret: false, placeholder: "123456789 (a group starts with -)" },
];

const INSTAGRAM_FIELDS: SectionField[] = [
  { key: "IG_USER_ID", label: "Instagram user ID", secret: false, placeholder: "17841400000000000" },
  { key: "IG_ACCESS_TOKEN", label: "Access token", secret: true, placeholder: "a long token from the Meta App Dashboard" },
];

const YOUTUBE_FIELDS: SectionField[] = [
  { key: "YT_CLIENT_ID", label: "OAuth client ID", secret: false, placeholder: "....apps.googleusercontent.com" },
  { key: "YT_CLIENT_SECRET", label: "OAuth client secret", secret: true, placeholder: "GOCSPX-..." },
  { key: "YT_REFRESH_TOKEN", label: "Refresh token", secret: true, placeholder: "1//..." },
];

export function UserIntegrations() {
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({});
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(() => {
    getIntegrations()
      .then((r) => { setStatuses(r.values); setLoadError(null); })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Couldn't load integration status."));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid gap-6">
      <div>
        <p className="label-mono">My Integrations</p>
        <h2 className="mt-1 font-heading text-2xl font-semibold tracking-tight">Your publishing accounts</h2>
        <p className="mt-2 max-w-prose text-sm text-muted-foreground">
          Connect your Telegram chat, Instagram account, and YouTube channel. These are stored securely and used only for your content.
        </p>
      </div>
      {loadError && <p className="rounded-md border border-bad/40 bg-bad/10 p-4 text-sm text-bad">{loadError}</p>}
      <IntegrationSection title="Telegram" fields={TELEGRAM_FIELDS} statuses={statuses} onSaved={load} />
      <IntegrationSection title="Instagram" fields={INSTAGRAM_FIELDS} statuses={statuses} onSaved={load} />
      <IntegrationSection title="YouTube" fields={YOUTUBE_FIELDS} statuses={statuses} onSaved={load} />
    </div>
  );
}
