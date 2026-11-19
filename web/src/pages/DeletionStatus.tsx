import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { CheckCircle2, AlertCircle, Clock, ShieldCheck, Search, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface DeletionStatusData {
  confirmation_code: string;
  status: "pending" | "completed" | "failed";
  platform: string;
  created_at: string | null;
  completed_at: string | null;
  message: string;
}

export default function DeletionStatus() {
  const [searchParams, setSearchParams] = useSearchParams();
  const codeParam = searchParams.get("code") || "";
  const [code, setCode] = useState(codeParam);
  const [data, setData] = useState<DeletionStatusData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async (lookupCode: string) => {
    if (!lookupCode.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/webhooks/meta/deletion-status?code=${encodeURIComponent(lookupCode.trim())}`);
      if (!res.ok) {
        if (res.status === 404) {
          throw new Error("Confirmation code not found. Please verify the code and try again.");
        }
        throw new Error(`Failed to fetch status (${res.status})`);
      }
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deletion status");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (codeParam) {
      setCode(codeParam);
      fetchStatus(codeParam);
    }
  }, [codeParam]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (code.trim()) {
      setSearchParams({ code: code.trim() });
      fetchStatus(code.trim());
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col justify-between py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-xl mx-auto w-full space-y-8">
        <div className="flex items-center justify-between">
          <Link to="/" className="inline-flex items-center text-xs font-mono text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-3.5 mr-1" /> Back to Dashboard
          </Link>
          <div className="inline-flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
            <ShieldCheck className="size-4 text-primary" /> Meta Compliance
          </div>
        </div>

        <div className="text-center space-y-2">
          <h1 className="text-2xl sm:text-3xl font-heading font-bold tracking-tight">Data Deletion Status</h1>
          <p className="text-sm text-muted-foreground">
            Verify the compliance and deletion status of your Instagram & Meta account data.
          </p>
        </div>

        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Enter confirmation code (e.g. del_meta_...)"
            className="font-mono text-xs"
          />
          <Button type="submit" disabled={loading || !code.trim()} size="sm">
            <Search className="size-3.5 mr-1.5" /> Verify
          </Button>
        </form>

        {loading && (
          <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground animate-pulse">
            Checking deletion certificate...
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-5 text-sm text-destructive flex items-start gap-3">
            <AlertCircle className="size-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Certificate Not Found</p>
              <p className="text-xs text-muted-foreground mt-1">{error}</p>
            </div>
          </div>
        )}

        {data && (
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-6">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider">Status Certificate</p>
                <p className="font-mono text-sm font-semibold mt-0.5">{data.confirmation_code}</p>
              </div>
              <div>
                {data.status === "completed" && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                    <CheckCircle2 className="size-3.5" /> Purged & Deleted
                  </span>
                )}
                {data.status === "pending" && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20">
                    <Clock className="size-3.5" /> Processing
                  </span>
                )}
                {data.status === "failed" && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20">
                    <AlertCircle className="size-3.5" /> Error
                  </span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <p className="text-muted-foreground font-mono">Platform</p>
                <p className="font-semibold capitalize mt-1">{data.platform}</p>
              </div>
              <div>
                <p className="text-muted-foreground font-mono">Completed At</p>
                <p className="font-semibold mt-1">
                  {data.completed_at ? new Date(data.completed_at).toLocaleString() : "In progress"}
                </p>
              </div>
            </div>

            <div className="rounded-lg bg-sunken/60 border border-border/50 p-4 text-xs text-muted-foreground space-y-1">
              <p className="font-semibold text-foreground">Compliance Confirmation</p>
              <p>{data.message}</p>
            </div>
          </div>
        )}
      </div>

      <div className="text-center text-xs text-muted-foreground pt-8">
        &copy; {new Date().getFullYear()} Mintly / CodexOne &middot; Meta Platform Terms Compliance Section 4.b
      </div>
    </div>
  );
}
