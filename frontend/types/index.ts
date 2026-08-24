export type DocStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "changes_requested"
  | "published";

export interface Repo {
  id: string;
  owner: string;
  name: string;
  fullName: string;
  connectedAt: string;
  webhookActive: boolean;
  lastWebhookAt?: string;
  gitbookSpaceId?: string;
}

export interface DocVersion {
  id: string;
  repoId: string;
  title: string;
  content: string;
  previousContent?: string;
  hasChanges?: boolean;
  status: DocStatus;
  createdAt: string;
  reviewComment?: string;
}