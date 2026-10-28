// Bootstraps the first admin: `npm run add-admin -w server -- "Garang Mabior"`.
// Prints the key once; only its hash is committed to GitHub.
import { changeUsers, makeUser } from '../auth';

const name = process.argv.slice(2).join(' ').trim();
if (name.split(/\s+/).length < 2) { console.error('Usage: add-admin "First Last"'); process.exit(1); }
let key = '', id = '';
const r = await changeUsers(`add admin (hash only)`, f => {
  const m = makeUser(f.users, name, 'Admin', 365);
  key = m.key; id = m.user.id;
  return { users: [m.user, ...f.users] };
});
console.log(`Admin ${id} added (commit ${r.commit.slice(0, 7)}).\nAccess key, shown once:\n\n  ${key}\n`);
