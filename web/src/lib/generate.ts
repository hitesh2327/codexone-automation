import { api } from "./api";
import type { GenConfig, GenerateRequest, Job, JobsResponse, GithubState, Slot } from "./generate-format";

export const getConfig = (signal?: AbortSignal) => api<GenConfig>("/api/generate/config", { signal });
export const getSlots = (signal?: AbortSignal) => api<{ now: string; slots: Slot[] }>("/api/generate/slots", { signal });
export const getJobs = (signal?: AbortSignal) => api<JobsResponse>("/api/generate/jobs?limit=20", { signal });
export const getJob = (id: string, signal?: AbortSignal) =>
  api<{ job: Job; github: GithubState }>(`/api/generate/jobs/${id}`, { signal });
export const checkTopic = (topic: string, signal?: AbortSignal) =>
  api<{ duplicate: { title: string; date: string } | null }>(`/api/generate/check?topic=${encodeURIComponent(topic)}`, { signal });
export type GroupJob = Pick<Job, "id" | "trigger" | "requested_by" | "created_at" | "status">;
export const getJobForGroup = (groupId: string, signal?: AbortSignal) =>
  api<{ job: GroupJob | null }>(`/api/generate/for-group?group_id=${encodeURIComponent(groupId)}`, { signal });
export const requestGeneration = (body: GenerateRequest) => api<Job>("/api/generate", { method: "POST", body });
