export function countFmt(count: number): string {
  return count.toLocaleString();
}

export function humanBytes(count: number): string {
  let value = count;
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  for (const unit of units) {
    if (value < 1024 || unit === "TiB") {
      if (unit === "B") return `${Math.round(value)} ${unit}`;
      return `${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${unit}`;
    }
    value /= 1024;
  }
  return `${count} B`;
}

export function formatDuration(totalSeconds: number): string {
  const total = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return hours > 0 ? `${hours}:${two(minutes)}:${two(seconds)}` : `${minutes}:${two(seconds)}`;
}

const DAY_FMT = new Intl.DateTimeFormat(undefined, { month: "long", day: "numeric", year: "numeric" });
const TIME_FMT = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" });
const MONTH_FMT = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" });

export function dayLabel(ts: number): string {
  return DAY_FMT.format(new Date(ts * 1000));
}

export function dayKey(ts: number): string {
  const date = new Date(ts * 1000);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function timeLabel(ts: number): string {
  return TIME_FMT.format(new Date(ts * 1000));
}

export function fullStamp(ts: number): string {
  return `${dayLabel(ts)} at ${timeLabel(ts)}`;
}

export function monthLabel(period: string): string {
  const [year, month] = period.split("-").map(Number);
  if (!month) return period;
  return MONTH_FMT.format(new Date(year, month - 1, 1));
}
