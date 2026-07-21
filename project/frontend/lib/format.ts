/** Decode a few common HTML entities without a DOM. */
function decodeBasicEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&apos;/gi, "'");
}

/**
 * Normalize any email body (HTML or plain) into Gmail-like readable text.
 * Collapses layout whitespace from marketing / table-based HTML emails.
 */
export function toPlainMessageText(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  let text = value;
  if (text.includes("<")) {
    text = text
      .replace(/<(script|style)[\s\S]*?<\/\1>/gi, "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/(p|div|tr|li|h[1-6]|td|th)>/gi, "\n")
      .replace(/<(p|div|tr|li|h[1-6]|td|th)\b[^>]*>/gi, "\n")
      .replace(/<a\b[^>]*>([\s\S]*?)<\/a>/gi, "$1")
      .replace(/<[^>]+>/g, "");
  }

  text = decodeBasicEntities(text)
    .replace(/\u00a0/g, " ")
    .replace(/\u200b/g, "")
    // Collapse space-padded HTML layout into normal sentences.
    .replace(/[ \t\f\v]+/g, " ");

  const lines: string[] = [];
  let previousBlank = false;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      if (!previousBlank) {
        lines.push("");
      }
      previousBlank = true;
      continue;
    }
    // Drop decorative separators from email templates.
    if (/^[-_=.*·•\s]{3,}$/.test(line)) {
      continue;
    }
    lines.push(line);
    previousBlank = false;
  }

  return lines.join("\n").trim();
}

/** One-line preview for collapsed mail rows. */
export function previewMessage(
  value: string | null | undefined,
  maxLength = 110,
): string {
  const plain = toPlainMessageText(value).replace(/\s+/g, " ").trim();
  if (!plain) {
    return "No message text";
  }
  if (plain.length <= maxLength) {
    return plain;
  }
  return `${plain.slice(0, maxLength - 1).trimEnd()}…`;
}

/** Shorten long Gmail thread ids for display. */
export function shortId(id: string, head = 8, tail = 4): string {
  if (id.length <= head + tail + 1) {
    return id;
  }
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

/** Relative time like "2h ago" with absolute tooltip text via formatTimestamp. */
export function formatRelativeTime(isoString: string): string {
  if (!isoString) {
    return "Unknown time";
  }

  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }

  const diffMs = Date.now() - date.getTime();
  const absMs = Math.abs(diffMs);
  const mins = Math.round(absMs / 60_000);
  const hours = Math.round(absMs / 3_600_000);
  const days = Math.round(absMs / 86_400_000);
  const suffix = diffMs >= 0 ? "ago" : "from now";

  if (mins < 1) {
    return "Just now";
  }
  if (mins < 60) {
    return `${mins}m ${suffix}`;
  }
  if (hours < 48) {
    return `${hours}h ${suffix}`;
  }
  return `${days}d ${suffix}`;
}

/** Format an ISO timestamp as dd/mm/yyyy, hh:mm. */
export function formatTimestamp(isoString: string): string {
  if (!isoString) {
    return "N/A";
  }

  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }

  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${day}/${month}/${year}, ${hours}:${minutes}`;
}

/** Format a number as USD currency with commas and 2 decimal places. */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}
