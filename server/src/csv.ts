// Small RFC 4180 parser: quoted fields, embedded commas and doubled quotes.
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; }
      else f += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(f); f = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(f); f = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else f += ch;
  }
  if (f !== '' || row.length) { row.push(f); rows.push(row); }
  return rows;
}

export function csvObjects(text: string): Record<string, string>[] {
  const [head, ...rest] = parseCsv(text);
  if (!head) return [];
  return rest.map(r => Object.fromEntries(head.map((h, i) => [h.trim(), r[i] ?? ''])));
}

export const num = (s: string | undefined) => (s === undefined || s.trim() === '' || isNaN(Number(s)) ? null : Number(s));
export const findCol = (cols: string[], re: RegExp) => cols.find(c => re.test(c));
