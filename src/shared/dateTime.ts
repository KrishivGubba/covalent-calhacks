const SYSTEM_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function formatSystemDateTime(
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = {},
): string {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    timeZone: SYSTEM_TIME_ZONE,
    ...options,
  }).format(date);
}

export function formatSystemTimestamp(
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = {},
): string {
  return formatSystemDateTime(value, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    ...options,
  });
}

export function getSystemTimeZone(): string {
  return SYSTEM_TIME_ZONE;
}
