import fs from "fs";

interface ReadRecentLineOptions {
  maxBytes?: number;
  chunkSize?: number;
}

const DEFAULT_MAX_BYTES = 8 * 1024 * 1024;
const DEFAULT_CHUNK_SIZE = 64 * 1024;

export function readRecentNonEmptyLines(
  file: string,
  maxLines: number,
  options: ReadRecentLineOptions = {}
): string[] {
  if (maxLines <= 0) return [];

  const maxBytes = Math.max(1, options.maxBytes ?? DEFAULT_MAX_BYTES);
  const chunkSize = Math.max(1, options.chunkSize ?? DEFAULT_CHUNK_SIZE);
  const stat = fs.statSync(file);
  const bytesToRead = Math.min(stat.size, maxBytes);
  if (bytesToRead === 0) return [];

  const fd = fs.openSync(file, "r");
  try {
    const chunks: Buffer[] = [];
    let remaining = bytesToRead;
    let position = stat.size - bytesToRead;

    while (remaining > 0) {
      const size = Math.min(chunkSize, remaining);
      const buffer = Buffer.allocUnsafe(size);
      fs.readSync(fd, buffer, 0, size, position);
      chunks.push(buffer);
      position += size;
      remaining -= size;
    }

    const text = Buffer.concat(chunks).toString("utf-8");
    const lines = text.split(/\r?\n/).filter(Boolean);
    return lines.slice(-maxLines);
  } finally {
    fs.closeSync(fd);
  }
}
