const ZONE = "Europe/London";

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: ZONE,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function words(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replaceAll("_", " ");
}

export function minutes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  if (hours <= 0) return `${mins}m`;
  return `${hours}h ${mins}m`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}
