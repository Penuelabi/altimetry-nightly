// Market: what the cooperative has for sale, the offers buyers make, and the sales that follow. Everything here is in the
// shared farm register (so every phone sees it, and it is copied to the Drive sheet tabs register_listings and register_offers).
import { useState } from 'react';
import { LISTINGS, adminLabel, balances, editAllowed, listingLeft, newId, salesTotal, type AdminLoc, type Listing, type Offer } from '@abuk/core';
import { farmChange, go, record, useApp } from '../store';
import { AdminPicker, useHereAdmin } from '../pickers';
import { Field } from '../ui';

const usd = (n: number) => `$${n.toLocaleString('en', { maximumFractionDigits: 2 })}`;
const dateOf = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
const noAdmin = (a: AdminLoc) => (!a.state || !a.county || !a.payam ? 'Choose the state, county and payam.' : '');

export function Market() {
  const s = useApp();
  const live = !!s.session && !s.session.demo;
  const can = live && editAllowed(s.session?.user.role ?? '');
  const reg = s.farm, listings = reg.listings ?? [], offers = reg.offers ?? [];
  const sales = salesTotal(reg, new Date().getFullYear());
  const farmers = reg.groups.reduce((n, g) => n + g.members.length, 0);
  const [form, setForm] = useState<'offer' | 'listing' | null>(null);
  const [msg, setMsg] = useState('');
  const [counter, setCounter] = useState<Record<string, string>>({});
  const bal = balances(reg);
  const by = s.session?.user.name ?? '';
  const sorted = [...offers].sort((a, b) => Number(b.status === 'open') - Number(a.status === 'open') || b.at.localeCompare(a.at));

  const answer = (o: Offer, status: Offer['status'], extra: Partial<Offer> = {}) => {
    const next: Offer = { ...o, status, answeredAt: new Date().toISOString(), ...extra };
    farmChange({ op: 'upsert', kind: 'offer', item: next });
    record('offer', { buyer: o.buyer, product: o.product, qty: o.qty, unit: o.unit, price: next.price, answer: status, counterPrice: next.counterPrice ?? null });
    setMsg(`${o.buyer}: ${status === 'accepted' ? `accepted at ${usd(next.price)} per ${o.unit}` : status === 'countered' ? `counter of ${usd(next.counterPrice ?? 0)} per ${o.unit} recorded. Tell the buyer, then tap "Buyer agrees" when they reply` : status === 'declined' ? 'declined' : 'marked delivered'}.`);
  };
  const deliver = (o: Offer) => {
    const l = listings.find(x => x.id === o.listingId);
    if (l?.storeId && l.itemId) {
      if (bal(l.storeId, l.itemId) < o.qty) return setMsg(`Not enough in the store: ${bal(l.storeId, l.itemId)} ${o.unit} left, the sale is ${o.qty}. Record a store movement first, or change the quantity.`);
      const moveId = newId('mv');
      farmChange({ op: 'upsert', kind: 'move', item: { id: moveId, storeId: l.storeId, itemId: l.itemId, date: new Date().toISOString().slice(0, 10), dir: 'out', qty: o.qty, party: o.buyer, orderId: '', by: s.session?.user.id ?? '', note: `Sale of ${o.product}` } });
      answer(o, 'delivered', { moveId });
      return;
    }
    answer(o, 'delivered');
  };

  return (
    <div className="pad">
      <div>
        <div className="kick muted">Cooperative sales · {new Date().getFullYear()}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}><span className="head num" style={{ fontSize: 42 }}>{live ? usd(sales.usd) : '$18,640'}</span><span style={{ fontSize: 12.5, color: 'var(--color-accent-700)' }}>{live ? `from ${sales.offers} agreed sale${sales.offers === 1 ? '' : 's'}${farmers ? `, to be shared across ${farmers} farmers by work days` : ''}` : 'sample figure'}</span></div>
        <div className="sub" style={{ marginTop: 4, lineHeight: 1.4 }}>{live ? 'Added up from the offers marked accepted or delivered below. It changes when you answer an offer.' : 'Demo: sample data. Sign in to see your project\'s own listings and offers.'}</div>
      </div>

      <div className="box col g6" style={{ padding: '10px 12px' }}>
        <div className="kick sm">What the Market is for</div>
        <div style={{ fontSize: 13, lineHeight: 1.5 }}>It is the cooperative's sales book. Put what you have ready to sell on the list, write down every offer a buyer makes, answer it, and mark it delivered. Delivered sales take the goods out of the store, and the total becomes the sale that is shared out under Field tools, Work days and payout.</div>
        <div style={{ fontSize: 12.5, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>To update: <strong style={{ fontWeight: 600 }}>1</strong> list stock (from the store, or something else) · <strong style={{ fontWeight: 600 }}>2</strong> record an offer when a buyer calls or messages · <strong style={{ fontWeight: 600 }}>3</strong> accept, counter or decline · <strong style={{ fontWeight: 600 }}>4</strong> mark delivered when the buyer collects.</div>
      </div>

      {msg && <div className="msg">{msg}</div>}

      {live && <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Offers · {offers.filter(o => o.status === 'open').length} open</h2>
        {sorted.map(o => (
          <div key={o.id} className="col g6" style={{ padding: '10px 0', borderBottom: '1px solid var(--color-divider)' }}>
            <div className="between"><span style={{ fontSize: 14 }}>{o.buyer}</span><span className="it" style={{ fontSize: 12.5, color: o.status === 'open' ? 'var(--color-accent-800)' : 'var(--color-neutral-700)' }}>{o.status}{o.status === 'countered' && o.counterPrice ? ` at ${usd(o.counterPrice)}` : ''}</span></div>
            <div className="sub">{o.qty} {o.unit} of {o.product} at {usd(o.price)} = {usd(o.qty * o.price)} · {dateOf(o.at)}{o.pickup ? ` · collect at ${o.pickup}` : ''}{o.phone ? <> · <a href={`tel:${o.phone}`}>{o.phone}</a></> : ''}{o.note ? ` · ${o.note}` : ''}</div>
            {can && o.status === 'open' && (
              <div className="col g6">
                <div className="grid2" style={{ gap: 8 }}>
                  <button className="btn md" onClick={() => answer(o, 'accepted')}>Accept · {usd(o.qty * o.price)}</button>
                  <button className="btn plain md" onClick={() => answer(o, 'declined')}>Decline</button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8 }}>
                  <input className="input num" type="number" inputMode="decimal" placeholder={`Counter price per ${o.unit}`} value={counter[o.id] ?? ''} onChange={e => setCounter({ ...counter, [o.id]: e.target.value })} />
                  <button className="btn plain md" disabled={!(Number(counter[o.id]) > 0)} onClick={() => answer(o, 'countered', { counterPrice: Number(counter[o.id]) })}>Counter</button>
                </div>
              </div>
            )}
            {can && o.status === 'countered' && (
              <div className="grid2" style={{ gap: 8 }}>
                <button className="btn md" onClick={() => answer(o, 'accepted', { price: o.counterPrice ?? o.price })}>Buyer agrees</button>
                <button className="btn plain md" onClick={() => answer(o, 'declined')}>Buyer walked away</button>
              </div>
            )}
            {can && o.status === 'accepted' && <button className="btn md" onClick={() => deliver(o)}>Mark delivered{listings.find(l => l.id === o.listingId)?.storeId ? ' and take it out of the store' : ''}</button>}
          </div>
        ))}
        {!offers.length && <div className="note" style={{ padding: '8px 0' }}>No offers yet. When a buyer asks for something, record it here.</div>}
        {can && form !== 'offer' && <button className="btn plain" style={{ marginTop: 8 }} onClick={() => { setForm('offer'); setMsg(''); }}>+ Record an offer</button>}
        {form === 'offer' && <OfferForm onDone={m => { setForm(null); setMsg(m); }} />}
      </div>}

      <div>
        <h2 className="h2 h20 rule" style={{ marginBottom: 2 }}>Our listings</h2>
        {live ? listings.map(l => {
          const left = listingLeft(reg, l);
          return (
            <div key={l.id} className="rowg" style={{ padding: '10px 0', alignItems: 'center' }}>
              <span><span style={{ display: 'block', fontSize: 14 }}>{l.name}</span><span className="sub">{l.status === 'open' ? `${left} of ${l.qty} ${l.unit} left` : l.status}{l.groupId ? ` · ${reg.groups.find(g => g.id === l.groupId)?.name ?? ''}` : ''}{l.admin ? ` · ${adminLabel(l.admin)}` : ''}{l.storeId ? ' · from the store' : ''}</span></span>
              <span style={{ textAlign: 'right' }}>
                <span className="head num" style={{ display: 'block', fontSize: 20 }}>{usd(l.price)}</span><span style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>per {l.unit}</span>
                {can && <button className="link" style={{ fontSize: 12 }} onClick={() => farmChange({ op: 'upsert', kind: 'listing', item: { ...l, status: l.status === 'open' ? 'withdrawn' : 'open' } })}>{l.status === 'open' ? 'Withdraw' : 'Re-open'}</button>}
              </span>
            </div>
          );
        }) : LISTINGS.map(l => (
          <div key={l.name} className="rowg" style={{ padding: '10px 0' }}>
            <span><span style={{ display: 'block', fontSize: 14 }}>{l.name}</span><span className="sub">{l.stock} in stock · {l.offers} · sample</span></span>
            <span style={{ textAlign: 'right' }}><span className="head num" style={{ display: 'block', fontSize: 20 }}>{l.price}</span><span style={{ fontSize: 11, color: 'var(--color-neutral-700)' }}>{l.unit}</span></span>
          </div>
        ))}
        {live && !listings.length && <div className="note" style={{ padding: '8px 0' }}>Nothing listed yet.{can ? ' Use "List produce" to put store stock or other produce on the list.' : ' A group lead or admin lists produce.'}</div>}
      </div>

      {form === 'listing' && <ListingForm onDone={m => { setForm(null); setMsg(m); }} />}
      <div className="grid2">
        <button className="btn plain" onClick={() => go('process')}>Stock & processing</button>
        <button className="btn" disabled={!can || form === 'listing'} onClick={() => { setForm('listing'); setMsg(''); }}>List produce</button>
      </div>
      {!can && <div className="sub">{live ? 'Listing produce and answering offers is for group leads and admins.' : 'Sign in to list produce.'}</div>}
    </div>
  );
}

function OfferForm({ onDone }: { onDone: (m: string) => void }) {
  const s = useApp();
  const open = (s.farm.listings ?? []).filter(l => l.status === 'open');
  const [f, setF] = useState({ listingId: open[0]?.id ?? '', product: '', unit: 'L', buyer: '', phone: '', qty: '', price: '', pickup: '', note: '' });
  const [err, setErr] = useState('');
  const l = open.find(x => x.id === f.listingId);
  const save = () => {
    const qty = Number(f.qty), price = Number(f.price || l?.price);
    if (!f.buyer.trim()) return setErr('Who is the buyer?');
    if (!l && !f.product.trim()) return setErr('What do they want to buy?');
    if (!(qty > 0)) return setErr('Enter the quantity they ask for.');
    if (!(price > 0)) return setErr('Enter the price per unit.');
    const o: Offer = { id: newId('of'), ...(l ? { listingId: l.id } : {}), buyer: f.buyer.trim(), phone: f.phone.trim(), product: l?.name ?? f.product.trim(), qty, unit: l?.unit ?? (f.unit.trim() || 'unit'), price, status: 'open', pickup: f.pickup.trim(), note: f.note.trim(), by: s.session?.user.name ?? '', at: new Date().toISOString() };
    farmChange({ op: 'upsert', kind: 'offer', item: o });
    onDone(`Offer from ${o.buyer} recorded: ${qty} ${o.unit} of ${o.product} at ${usd(price)}.`);
  };
  return (
    <div className="box col g8" style={{ padding: 12, marginTop: 8 }}>
      <div className="kick sm">Record an offer</div>
      <Field label="Buyer"><input className="input" value={f.buyer} onChange={e => { setF({ ...f, buyer: e.target.value }); setErr(''); }} /></Field>
      <Field label="Buyer's phone (optional)"><input className="input num" inputMode="tel" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} /></Field>
      <Field label="Product"><select className="input" value={f.listingId} onChange={e => setF({ ...f, listingId: e.target.value })}>{open.map(x => <option key={x.id} value={x.id}>{x.name} · {usd(x.price)} per {x.unit}</option>)}<option value="">Something not listed…</option></select></Field>
      {!l && <div className="grid2"><Field label="Product name"><input className="input" value={f.product} onChange={e => setF({ ...f, product: e.target.value })} /></Field><Field label="Unit"><input className="input" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })} /></Field></div>}
      <div className="grid2">
        <Field label={`Quantity${l ? ` (${l.unit})` : ''}`}><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => { setF({ ...f, qty: e.target.value }); setErr(''); }} /></Field>
        <Field label="Price offered per unit ($)"><input className="input num" type="number" inputMode="decimal" placeholder={l ? String(l.price) : ''} value={f.price} onChange={e => { setF({ ...f, price: e.target.value }); setErr(''); }} /></Field>
      </div>
      <Field label="Collect at (optional)"><input className="input" value={f.pickup} onChange={e => setF({ ...f, pickup: e.target.value })} /></Field>
      <Field label="Note (optional)"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <div className="grid2"><button className="btn plain" onClick={() => onDone('')}>Cancel</button><button className="btn" onClick={save}>Save offer</button></div>
    </div>
  );
}

function ListingForm({ onDone }: { onDone: (m: string) => void }) {
  const s = useApp(), here = useHereAdmin();
  const bal = balances(s.farm);
  const stock = (s.farm.stores ?? []).flatMap(st => (s.farm.items ?? []).map(it => ({ st, it, n: bal(st.id, it.id) }))).filter(x => x.n > 0);
  const [f, setF] = useState({ from: stock[0] ? `${stock[0].st.id}|${stock[0].it.id}` : '', name: '', unit: 'kg', qty: '', price: '', groupId: '', admin: here as AdminLoc, note: '' });
  const [err, setErr] = useState('');
  const pick = stock.find(x => `${x.st.id}|${x.it.id}` === f.from);
  const save = () => {
    const qty = Number(f.qty), price = Number(f.price);
    if (!pick && !f.name.trim()) return setErr('What are you listing?');
    if (!(qty > 0)) return setErr('Enter the quantity.');
    if (pick && qty > pick.n) return setErr(`Only ${pick.n} ${pick.it.unit} of ${pick.it.name} is in ${pick.st.name}.`);
    if (!(price >= 0) || f.price === '') return setErr('Enter the price per unit in dollars.');
    const bad = noAdmin(f.admin);
    if (bad) return setErr(bad);
    const l: Listing = { id: newId('ls'), name: pick?.it.name ?? f.name.trim(), ...(pick ? { storeId: pick.st.id, itemId: pick.it.id } : {}), qty, unit: pick?.it.unit ?? (f.unit.trim() || 'unit'), price, ...(f.groupId ? { groupId: f.groupId } : {}), admin: f.admin, status: 'open', note: f.note.trim(), by: s.session?.user.name ?? '', at: new Date().toISOString() };
    farmChange({ op: 'upsert', kind: 'listing', item: l });
    onDone(`${l.name}: ${qty} ${l.unit} listed at ${usd(price)} per ${l.unit}.`);
  };
  return (
    <div className="box col g8" style={{ padding: 12 }}>
      <div className="kick sm">List produce</div>
      <Field label="What"><select className="input" value={f.from} onChange={e => { setF({ ...f, from: e.target.value }); setErr(''); }}>{stock.map(x => <option key={`${x.st.id}|${x.it.id}`} value={`${x.st.id}|${x.it.id}`}>{x.it.name} · {x.n} {x.it.unit} in {x.st.name}</option>)}<option value="">Something not in a store…</option></select></Field>
      {!pick && <div className="grid2"><Field label="Product name"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field><Field label="Unit"><input className="input" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })} /></Field></div>}
      <div className="grid2">
        <Field label={`Quantity${pick ? ` (${pick.it.unit})` : ''}`}><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => { setF({ ...f, qty: e.target.value }); setErr(''); }} /></Field>
        <Field label="Price per unit ($)"><input className="input num" type="number" inputMode="decimal" value={f.price} onChange={e => { setF({ ...f, price: e.target.value }); setErr(''); }} /></Field>
      </div>
      <Field label="Group (optional)"><select className="input" value={f.groupId} onChange={e => setF({ ...f, groupId: e.target.value })}><option value="">—</option>{s.farm.groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
      <AdminPicker value={f.admin} onChange={admin => { setF({ ...f, admin }); setErr(''); }} label="Where it is" />
      <Field label="Note (optional)"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <div className="grid2"><button className="btn plain" onClick={() => onDone('')}>Cancel</button><button className="btn" onClick={save}>List it</button></div>
    </div>
  );
}
