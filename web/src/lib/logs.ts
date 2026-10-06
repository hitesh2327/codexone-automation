import { api } from "./api";
import { logsQuery, type LogFilters, type LogsResponse, type Summary } from "./log-format";

export * from "./log-format";

export const listLogs = (filters: LogFilters, opts: { before_id?: number | null; limit?: number } = {}, signal?: AbortSignal) =>
  api<LogsResponse>(`/api/logs${logsQuery(filters, opts)}`, { signal });

export const logsSummary = (signal?: AbortSignal) => api<Summary>("/api/logs/summary", { signal });
