// Flood alerts to the people and groups on the shared register, the email list and WhatsApp groups.
// Everything leaves from this phone's own Messages, mail and WhatsApp apps: the app fills in the
// recipients and text, the person presses Send.
import { useState } from 'react';
import { adminLabel, newId, personById, personName, removeAllowed, type LeadAlert, type Person } from '@abuk/core';
import { farmChange, record, useApp } from '../store';
import { copyText, mailLink, openLink, smsLink, whatsappShare } from '../sms';
import { Field, Seg } from '../ui';

type AlertFor = (lead: { id: string; name: string; group: string; rows: string }) => LeadAlert;
const LEVEL = { warn: 'Warning', watch: 'Watch', clear: 'All clear' } as const;
const phonesOf = (p?: Person) => (p ? [p.phone, p.phone2].filter(Boolean) : []);

export function RegisterAlerts({ alertFor, canSend, canEdit }: { alertFor: AlertFor; canSend: boolean; canEdit: boolean }) {
  const s = useApp();
  const [lang, setLang] = useState<'en' | 'ar'>('en');
  const [open, setOpen] = useState<string | null>(null);
  const [msg, setMsg] = useState('');
  const role = s.session?.user.role ?? '';
  const reg = s.farm;

  // One broadcast text for the whole project (all plots) for email, WhatsApp and VSLA groups.
  const all = alertFor({ id: 'all', name: 'Abuk project', group: 'All groups', rows: reg.plots.map(p => p.code).join(' ') });
  const allText = lang === 'ar' ? all.ar : all.en;

  const groups = reg.groups.map(g => {
    const people = g.members.map(m => ({ m, p: personById(reg, m.personId) }));
    const phones = [...new Set(people.flatMap(({ p }) => (p?.phone ? [p.phone] : [])))];
    return { g, people, phones, a: alertFor({ id: g.id, name: g.lead || g.name, group: g.name, rows: '' }) };
  }).filter(x => x.g.members.length);
  const vsla = (reg.vslaGroups ?? []).map(v => {
    const people = (v.memberIds ?? []).map(id => personById(reg, id)).filter((p): p is Person => !!p);
    return { v, people, phones: [...new Set(people.map(p => p.phone).filter(Boolean))] };
  }).filter(x => x.people.length);

  const sendSms = (phones: string[], text: string, ids: string[], level: string, label: string) => {
    openLink(smsLink(phones, text));
    record('alert', { channel: 'sms-register', lang, to: ids, text, level });
    setMsg(`Messages opened for ${label}. Press Send there; the text goes from this phone's SIM.`);
  };

  const subs = reg.subscribers ?? [], on = subs.filter(x => x.on);
  const [sub, setSub] = useState({ name: '', email: '' });
  const [wa, setWa] = useState({ name: '', link: '' });
  const [err, setErr] = useState('');
  const addSub = () => {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(sub.email.trim())) return setErr('Enter a valid email address.');
    if (subs.some(x => x.email.toLowerCase() === sub.email.trim().toLowerCase())) return setErr('That address is already on the list.');
    farmChange({ op: 'upsert', kind: 'subscriber', item: { id: newId('sub'), name: sub.name.trim() || sub.email.trim(), email: sub.email.trim(), on: true } });
    setSub({ name: '', email: '' }); setErr('');
  };
  const addWa = () => {
    if (!wa.name.trim() || !/^https:\/\/chat\.whatsapp\.com\/[A-Za-z0-9]+/.test(wa.link.trim())) return setErr('Give the group a name and paste its invite link (https://chat.whatsapp.com/…).');
    farmChange({ op: 'upsert', kind: 'waGroup', item: { id: newId('wa'), name: wa.name.trim(), link: wa.link.trim() } });
    setWa({ name: '', link: '' }); setErr('');
  };
  const sendWa = async (name: string, link: string, id: string) => {
    const ok = await copyText(allText);
    record('alert', { channel: 'whatsapp', lang, to: [id], text: allText, level: all.level });
    openLink(link);
    setMsg(ok ? `The alert text is copied. In ${name}, paste it and press Send.` : `WhatsApp opened for ${name}. Paste the alert text there (it could not be copied automatically).`);
  };

  return (
    <div className="col g14">
      <div className="between rule-b" style={{ paddingBottom: 4 }}>
        <span className="kick sm">From the people register</span>
        <Seg items={[['en', 'English'], ['ar', 'Arabic']]} value={lang} onPick={setLang} fontSize={11.5} />
      </div>

      <div>
        <div className="section">Groups and members · phones come from each person's record</div>
        {groups.map(({ g, people, phones, a }) => {
          const text = lang === 'ar' ? a.ar : a.en;
          return (
            <div key={g.id} style={{ borderBottom: '1px solid var(--color-divider)', padding: '10px 0' }}>
              <button className="between" style={{ width: '100%', textAlign: 'left', background: 'none', border: 0, padding: 0, alignItems: 'baseline' }} onClick={() => setOpen(open === g.id ? null : g.id)}>
                <span><span style={{ display: 'block', fontSize: 14 }}>{g.name}{g.lead ? ` · lead ${g.lead}` : ''}</span><span className="sub num">{phones.length} of {g.members.length} members have a phone on file</span></span>
                <span className="it" style={{ fontSize: 12.5, color: a.level === 'clear' ? 'var(--color-neutral-600)' : 'var(--color-accent-800)' }}>{LEVEL[a.level]}</span>
              </button>
              {open === g.id && (
                <div className="col g8" style={{ marginTop: 8 }}>
                  <div dir={lang === 'ar' ? 'rtl' : undefined} className={lang === 'ar' ? '' : 'mono'} style={{ border: '1px solid var(--color-neutral-800)', borderRadius: 12, padding: 12, background: 'var(--color-neutral-100)', fontSize: 12.5, lineHeight: 1.5 }}>{text}</div>
                  {canSend && phones.length > 0 && <button className="btn md" onClick={() => sendSms(phones, text, people.flatMap(x => (x.p ? [x.p.id] : [])), a.level, g.name)}>Text all {phones.length} members of {g.name}</button>}
                  {people.map(({ m, p }) => (
                    <div key={m.id} className="rowg" style={{ alignItems: 'center', padding: '4px 0' }}>
                      <span><span style={{ display: 'block', fontSize: 13.5 }}>{m.name}</span><span className="sub num">{p ? (phonesOf(p).join(' · ') || 'no phone on file') : 'no personal details yet'}{p ? ` · ${adminLabel(p.admin)}` : ''}</span></span>
                      {canSend && p?.phone && <button className="btn plain sm" onClick={() => sendSms([p.phone], text, [p.id], a.level, personName(p))}>Text</button>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {!groups.length && <div className="note" style={{ padding: '8px 0' }}>No groups with members yet. Add members in the Farm register.</div>}
        {vsla.map(({ v, people, phones }) => (
          <div key={v.id} className="rowg" style={{ alignItems: 'center', padding: '8px 0' }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{v.name} (VSLA)</span><span className="sub num">{phones.length} of {people.length} members have a phone</span></span>
            {canSend && phones.length > 0 && <button className="btn plain sm" onClick={() => sendSms(phones, allText, people.map(p => p.id), all.level, v.name)}>Text all</button>}
          </div>
        ))}
      </div>

      <div className="box col g8" style={{ padding: 12 }}>
        <div className="between"><span className="kick sm">Alert text for email and WhatsApp</span><span className="it" style={{ fontSize: 12.5, color: 'var(--color-accent-800)' }}>{LEVEL[all.level]}</span></div>
        <div dir={lang === 'ar' ? 'rtl' : undefined} style={{ fontSize: 12.5, lineHeight: 1.5 }}>{allText}</div>
      </div>

      <div>
        <div className="section">Email subscribers · {on.length} of {subs.length} on</div>
        {subs.map(x => (
          <div key={x.id} className="rowg" style={{ alignItems: 'center', padding: '6px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{x.name}</span><span className="sub">{x.email}</span></span>
            <span style={{ display: 'flex', gap: 6 }}>
              {canEdit && <button className="btn plain sm" onClick={() => farmChange({ op: 'upsert', kind: 'subscriber', item: { ...x, on: !x.on } })}>{x.on ? 'On' : 'Off'}</button>}
              {removeAllowed(role) && <button className="btn plain sm" aria-label={`Remove ${x.name}`} onClick={() => farmChange({ op: 'remove', kind: 'subscriber', id: x.id })}>×</button>}
            </span>
          </div>
        ))}
        {canSend && on.length > 0 && <button className="btn md" style={{ marginTop: 6 }} onClick={() => { openLink(mailLink(on.map(x => x.email), `Abuk flood alert · ${LEVEL[all.level]}`, allText)); record('alert', { channel: 'email', lang, to: on.map(x => x.id), text: allText, level: all.level }); setMsg('Your mail app opened with the subscribers in Bcc. Press Send there.'); }}>Email the alert to {on.length} subscribers</button>}
        {canEdit && (
          <div className="col g8" style={{ marginTop: 8 }}>
            <div className="grid2"><Field label="Name"><input className="input" value={sub.name} onChange={e => setSub({ ...sub, name: e.target.value })} /></Field><Field label="Email"><input className="input" type="email" inputMode="email" value={sub.email} onChange={e => { setSub({ ...sub, email: e.target.value }); setErr(''); }} /></Field></div>
            <button className="btn plain" onClick={addSub}>+ Add to the email list</button>
          </div>
        )}
        {!subs.length && !canEdit && <div className="note">No subscribers yet. An admin or group lead can add them.</div>}
      </div>

      <div>
        <div className="section">WhatsApp groups · {(reg.waGroups ?? []).length}</div>
        {(reg.waGroups ?? []).map(x => (
          <div key={x.id} className="rowg" style={{ alignItems: 'center', padding: '6px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{x.name}</span><span className="sub">invite link saved</span></span>
            <span style={{ display: 'flex', gap: 6 }}>
              {canSend && <button className="btn plain sm" onClick={() => sendWa(x.name, x.link, x.id)}>Copy alert and open</button>}
              {removeAllowed(role) && <button className="btn plain sm" aria-label={`Remove ${x.name}`} onClick={() => farmChange({ op: 'remove', kind: 'waGroup', id: x.id })}>×</button>}
            </span>
          </div>
        ))}
        {canSend && <button className="btn plain" style={{ marginTop: 6 }} onClick={() => { openLink(whatsappShare(allText)); record('alert', { channel: 'whatsapp-share', lang, to: [], text: allText, level: all.level }); }}>Share the alert on WhatsApp (choose the chat)</button>}
        {canEdit && (
          <div className="col g8" style={{ marginTop: 8 }}>
            <div className="grid2"><Field label="Group name"><input className="input" value={wa.name} onChange={e => setWa({ ...wa, name: e.target.value })} /></Field><Field label="Invite link"><input className="input" placeholder="https://chat.whatsapp.com/…" value={wa.link} onChange={e => { setWa({ ...wa, link: e.target.value }); setErr(''); }} /></Field></div>
            <button className="btn plain" onClick={addWa}>+ Add a WhatsApp group</button>
          </div>
        )}
        <div className="sub" style={{ marginTop: 6, lineHeight: 1.5 }}>WhatsApp does not let an app message a group by itself. The button copies the alert and opens the group; paste and press Send.</div>
      </div>
      {err && <div className="msg">{err}</div>}
      {msg && <div className="msg">{msg}</div>}
    </div>
  );
}
