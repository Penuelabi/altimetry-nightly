// Placeholder QR pattern from the design: real finder squares, seeded noise inside.
// Swap for a real encoder once the trace URL scheme is fixed.
export function qrCells(seed: string) {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const out: { x: number; y: number }[] = [];
  const fin = (x: number, y: number) => (x < 7 && y < 7) || (x > 17 && y < 7) || (x < 7 && y > 17);
  for (let y = 0; y < 25; y++) for (let x = 0; x < 25; x++) {
    let on: boolean;
    if (fin(x, y)) {
      const lx = x > 17 ? x - 18 : x, ly = y > 17 ? y - 18 : y;
      on = lx === 0 || ly === 0 || lx === 6 || ly === 6 || (lx > 1 && lx < 5 && ly > 1 && ly < 5);
    } else { h = (h * 1103515245 + 12345) >>> 0; on = (h >>> 16) % 2 === 0; }
    if (on) out.push({ x, y });
  }
  return out;
}
