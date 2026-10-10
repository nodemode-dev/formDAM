export interface Media {
  id: number;
  sha256: string;
  rel_path: string;
  name: string;
  size: number;
  kind: "image" | "video";
  mime: string;
  width: number | null;
  height: number | null;
  duration: number | null;
  created_ts: number;
  imported_ts: number;
  favorite: boolean;
  private: boolean;
  trashed_ts: number | null;
  trash_reason: string | null;
  viewed_ts: number | null;
  is_screenshot: boolean;
  is_screen_rec: boolean;
  hidden: boolean;
  live_video_id?: number | null;
  live_of?: number | null;
  days_left?: number;
  pair_sim?: number;
  albums?: Array<{ id: number; name: string }>;
  make?: string | null;
  model?: string | null;
  lens?: string | null;
  focal?: number | null;
  focal35?: number | null;
  aperture?: number | null;
  shutter?: number | null;
  iso?: number | null;
  flash?: number | null;
  lat?: number | null;
  lon?: number | null;
  alt?: number | null;
  place?: string | null;
  admin?: string | null;
  country?: string | null;
  location_hidden?: number;
  content_id?: string | null;
  burst_id?: string | null;
  camera_type?: string | null;
  capture_type?: string | null;
  fps?: number | null;
  is_raw?: number;
  is_panorama?: number;
  is_selfie?: number;
  is_portrait?: number;
  is_slomo?: number;
  rating?: number;
  label?: string | null;
  rejected?: number;
  title?: string | null;
  caption?: string | null;
  alt_text?: string | null;
  edit_json?: string | null;
  edited_ts?: number | null;
  trim_in?: number | null;
  trim_out?: number | null;
  stack_id?: number | null;
  batch_id?: number | null;
  referenced?: number;
  created_src?: string;
  ocr_text?: string | null;
}

export interface MediaDetails extends Media {
  exif: Record<string, string>;
  iptc: Record<string, string>;
  keywords: Array<{ id: number; name: string }>;
  people: Array<{ id: number; name: string | null }>;
  subjects: Array<{ label: string; kind: string; score: number }>;
  batch: { id: number; source: string; label: string | null; started_ts: number } | null;
}

export interface MediaPage {
  items: Media[];
  next: Record<string, unknown> | null;
}

export interface PeriodSummary {
  level: string;
  periods: Array<{ period: string; count: number; covers: number[] }>;
}

export interface Album {
  id: number;
  name: string;
  is_private: boolean;
  count: number;
  cover_media_id: number | null;
  items?: Media[];
}

export interface Person {
  id: number;
  name: string | null;
  faces: number;
  media: number;
  cover_face_id: number | null;
  hidden?: boolean;
}

export interface PeopleStatus {
  cv2: boolean;
  models: boolean;
  missing_models: string[];
  ffmpeg: boolean;
  ready: boolean;
  threshold: number;
  pending_media: number;
  job: JobState | null;
}

export interface JobState {
  id: string;
  kind: string;
  phase: "running" | "done" | "error";
  counts: Record<string, number>;
  error: string;
}

export interface DupSet {
  id: number;
  match_kind: "exact" | "visual";
  similarity: number;
  keeper: Media;
  members: Media[];
}

export interface LibrarySummary {
  total: number;
  photos: number;
  videos: number;
  screenshots: number;
  screenrecs: number;
  favorites: number;
  recently_viewed: number;
  trash: number;
  albums: number;
  people: number;
  dup_sets: number;
  hidden: number;
}

export type FilterName =
  | "all"
  | "favorites"
  | "photos"
  | "videos"
  | "screenshots"
  | "screenrecs"
  | "not_in_album"
  | "recently_saved"
  | "recently_viewed"
  | `spec:${string}`;
