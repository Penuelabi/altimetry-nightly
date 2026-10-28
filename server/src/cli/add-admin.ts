// Bootstraps the first admin: `npm run add-admin -w server -- "Garang Mabior"` (one name is fine).
// Prints the key once; only its hash is committed to GitHub. With ADMIN_KEY_FILE set
// (used by the deploy workflow) the key goes to that file instead of stdout, and
// nothing is added if an admin already exists.
import { writeFileSync } from 'node:fs';
import { changeUsers, loadUsers, makeUser } from '../auth';

const name = process.argv.slice(2).join(' ').trim();
const keyFile = process.env.ADMIN_KEY_FILE;
try {
  if (!name) { console.error('Usage: add-admin "Full Name"'); process.exit(1); }
  if (keyFile && (await loadUsers(true)).users.some(u => u.role === 'Admin' && u.on)) { console.log('An admin already exists; nothing to do.'); process.exit(0); }
  let key = '', id = '';
  const r = await changeUsers(`add admin (hash only)`, f => {
    const m = makeUser(f.users, name, 'Admin', 365);
    key = m.key; id = m.user.id;
    return { users: [m.user, ...f.users] };
  });
  if (keyFile) { writeFileSync(keyFile, key, { mode: 0o600 }); console.log(`Admin ${id} added (commit ${r.commit.slice(0, 7)}); key stored, not printed.`); }
  else console.log(`Admin ${id} added (commit ${r.commit.slice(0, 7)}).\nAccess key, shown once:\n\n  ${key}\n`);
} catch (e) {
  console.error(`add-admin failed: ${(e as Error).message}`);
  process.exit(1);
}
