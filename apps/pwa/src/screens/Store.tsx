import { useState } from 'react';
import { ORDER_STATUS, balances, editAllowed, newId, seedStore, type Order, type OrderStatus, type StockItem, type StockMove, type Store as StoreT } from '@abuk/core';
import { farmChange, useApp } from '../store';
import { usePlace } from '../net';
import { Field, Seg } from '../ui';

// Seed & input store: balance per store, every movement in or out, and orders with a status trail.
// Everything lives in the shared farm register, so it works offline and syncs like the rest.
const today = () => new Date().toISOString().slice(0, 10);
const fmt = (d: string) => new Date(d.length === 10 ? d + 'T12:00:00' : d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' });
const qtyOf = (n: number, unit: string) => `${n.toLocaleString('en')} ${unit}`;

export function Store() {
  const s = useApp();
  // A register saved on this phone before the store existed starts from the standard store and items.
  const seed = seedStore();
  const stores = s.farm.stores ?? seed.stores, items = s.farm.items ?? seed.items, moves = s.farm.moves ?? [], orders = s.farm.orders ?? [];
  const [tab, setTab] = useState<'balance' | 'moves' | 'orders'>('balance');
  const [storeId, setStoreId] = useState(stores[0]?.id ?? '');
  const [form, setForm] = useState<null | { kind: 'move'; dir: 'in' | 'out'; itemId: string } | { kind: 'order'; itemId: string; qty: number } | { kind: 'store' } | { kind: 'item' } | { kind: 'status'; order: Order }>(null);
  const [msg, setMsg] = useState('');
  const can = editAllowed(s.session?.user.role ?? '');
  const bal = balances(s.farm);
  const store = stores.find(x => x.id === storeId) ?? stores[0];
  const itemOf = (id: string) => items.find(i => i.id === id);
  const done = (m: string) => { setForm(null); setMsg(m); };

  if (form?.kind === 'move' && store) return <MoveForm store={store} stores={stores} items={items} dir={form.dir} itemId={form.itemId} have={bal} onCancel={() => setForm(null)} onSaved={done} />;
  if (form?.kind === 'order') return <OrderForm stores={stores} items={items} storeId={store?.id ?? ''} itemId={form.itemId} qty={form.qty} onCancel={() => setForm(null)} onSaved={done} />;
  if (form?.kind === 'status') return <StatusForm order={form.order} item={itemOf(form.order.itemId)} onCancel={() => setForm(null)} onSaved={done} />;
  if (form?.kind === 'store') return <StoreForm onCancel={() => setForm(null)} onSaved={(m, id) => { setStoreId(id); done(m); }} />;
  if (form?.kind === 'item') return <ItemForm onCancel={() => setForm(null)} onSaved={done} />;

  const low = store ? items.filter(i => i.reorder != null && bal(store.id, i.id) < i.reorder) : [];
  const open = orders.filter(o => o.status !== 'received' && o.status !== 'cancelled');
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <div className="grid2" style={{ alignItems: 'end' }}>
        <Field label="Store"><select className="input" value={store?.id ?? ''} onChange={e => setStoreId(e.target.value)}>{stores.map(x => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></Field>
        {can && <button className="btn plain" onClick={() => setForm({ kind: 'store' })}>+ New store</button>}
      </div>
      {store && (store.place || store.keeper) && <div className="sub">{[store.place, store.keeper && `keeper ${store.keeper}`].filter(Boolean).join(' · ')}</div>}
      <Seg items={[['balance', 'Balance'], ['moves', 'In / out'], ['orders', `Orders${open.length ? ` (${open.length})` : ''}`]]} value={tab} onPick={v => setTab(v as typeof tab)} fontSize={12.5} />
      {msg && <div className="msg">{msg}</div>}

      {tab === 'balance' && store && <>
        <div style={{ borderTop: '1px solid var(--color-divider)' }}>
          {items.map(i => {
            const have = bal(store.id, i.id), isLow = i.reorder != null && have < i.reorder;
            return (
              <div key={i.id} className="col" style={{ padding: '10px 0', borderBottom: '1px solid var(--color-divider)', gap: 5 }}>
                <div className="between"><span style={{ fontSize: 14 }}>{i.name} <span className="sub num">{i.code}</span></span><span className="head num" style={{ fontSize: 19 }}>{qtyOf(have, i.unit)}</span></div>
                {i.reorder != null && <div style={{ position: 'relative', height: 7, border: '1px solid var(--color-divider)', borderRadius: 2 }}><span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: Math.max(0, Math.min(100, have / i.reorder * 100)) + '%', background: isLow ? 'var(--color-accent-300)' : 'var(--color-neutral-400)' }} /></div>}
                <div className="between" style={{ alignItems: 'center' }}>
                  <span style={{ fontSize: 11.5, color: isLow ? 'var(--color-accent-800)' : 'var(--color-neutral-700)' }}>{i.reorder == null ? i.kind : isLow ? `below ${qtyOf(i.reorder, i.unit)} needed` : `needed ${qtyOf(i.reorder, i.unit)}`}</span>
                  <span style={{ display: 'flex', gap: 6 }}>
                    <button className="btn plain" style={{ minHeight: 30, padding: '0 10px', fontSize: 12 }} onClick={() => setForm({ kind: 'move', dir: 'in', itemId: i.id })}>In</button>
                    <button className="btn plain" style={{ minHeight: 30, padding: '0 10px', fontSize: 12 }} disabled={have <= 0} onClick={() => setForm({ kind: 'move', dir: 'out', itemId: i.id })}>Out</button>
                  </span>
                </div>
              </div>
            );
          })}
          {!items.length && <div className="note" style={{ padding: '8px 0' }}>No items yet.</div>}
        </div>
        {can && <button className="btn plain" onClick={() => setForm({ kind: 'item' })}>+ New item</button>}
        {low.length > 0 && <button className="btn" onClick={() => {
          const ops = low.map(i => { const o = newOrder(i.id, (i.reorder ?? 0) - bal(store.id, i.id), store.id, '', s.session?.user.id ?? '', 'project office'); return { op: 'upsert' as const, kind: 'order' as const, item: o }; });
          farmChange(...ops); setTab('orders'); setMsg(`${ops.length} order${ops.length > 1 ? 's' : ''} requested for the short items.`);
        }}>Order {low.length} short item{low.length > 1 ? 's' : ''}</button>}
      </>}

      {tab === 'moves' && <div style={{ borderTop: '1px solid var(--color-divider)' }}>
        {moves.filter(m => !store || m.storeId === store.id).sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id)).slice(0, 60).map(m => {
          const i = itemOf(m.itemId);
          return (
            <div key={m.id} className="rowg" style={{ padding: '8px 0' }}>
              <span><span style={{ display: 'block', fontSize: 13.5 }}>{i?.name ?? m.itemId}</span><span className="sub num">{fmt(m.date)} · {m.dir === 'in' ? 'from' : 'to'} {m.party || '—'}{m.orderId ? ` · order ${orders.find(o => o.id === m.orderId)?.code ?? ''}` : ''} · {m.by}</span></span>
              <span className="num" style={{ fontSize: 14, color: m.dir === 'in' ? 'var(--color-text)' : 'var(--color-accent-800)' }}>{m.dir === 'in' ? '+' : '−'}{qtyOf(m.qty, i?.unit ?? '')}</span>
            </div>
          );
        })}
        {!moves.some(m => !store || m.storeId === store.id) && <div className="note" style={{ padding: '8px 0' }}>No movements yet. Start with an opening count: tap In on each item and enter what is on the shelf.</div>}
      </div>}

      {tab === 'orders' && <>
        <button className="btn" onClick={() => setForm({ kind: 'order', itemId: items[0]?.id ?? '', qty: 0 })}>+ New order</button>
        <div style={{ borderTop: '1px solid var(--color-divider)' }}>
          {[...orders].sort((a, b) => b.created.localeCompare(a.created)).map(o => {
            const i = itemOf(o.itemId), last = o.history[o.history.length - 1];
            return (
              <button key={o.id} className="rowg hov" style={{ width: '100%', textAlign: 'left', padding: '9px 0', background: 'none', border: 0, borderBottom: '1px solid var(--color-divider)' }} onClick={() => setForm({ kind: 'status', order: o })}>
                <span><span style={{ display: 'block', fontSize: 13.5 }}>{o.code} · {i?.name ?? o.itemId} · {qtyOf(o.qty, i?.unit ?? '')}</span><span className="sub">{o.where ? `now at ${o.where} · ` : ''}{last ? `${fmt(last.at)} by ${last.by}` : fmt(o.created)}{o.supplier ? ` · ${o.supplier}` : ''}</span></span>
                <span className="it" style={{ fontSize: 12.5, color: o.status === 'received' ? 'var(--color-neutral-600)' : 'var(--color-accent-800)' }}>{o.status}</span>
              </button>
            );
          })}
          {!orders.length && <div className="note" style={{ padding: '8px 0' }}>No orders yet.</div>}
        </div>
      </>}
    </div>
  );
}

function newOrder(itemId: string, qty: number, storeId: string, supplier: string, by: string, where: string): Order {
  const at = new Date().toISOString();
  const code = `ORD-${at.slice(2, 4)}${at.slice(5, 7)}${at.slice(8, 10)}-${Math.random().toString(36).slice(2, 5).toUpperCase()}`;
  return { id: newId('ord'), code, itemId, qty: Math.round(qty * 100) / 100, storeId, supplier, created: at, by, status: 'requested', where, history: [{ at, status: 'requested', where, by, note: '' }] };
}

const Buttons = ({ onCancel, onSave, label }: { onCancel: () => void; onSave: () => void; label: string }) => (
  <div className="grid2" style={{ gap: 8 }}><button className="btn plain" onClick={onCancel}>Cancel</button><button className="btn" onClick={onSave}>{label}</button></div>
);

function MoveForm({ store, stores, items, dir, itemId, have, onCancel, onSaved }: { store: StoreT; stores: StoreT[]; items: StockItem[]; dir: 'in' | 'out'; itemId: string; have: (s: string, i: string) => number; onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp();
  const [f, setF] = useState({ storeId: store.id, itemId, dir, date: today(), qty: '', party: '', note: '' });
  const [err, setErr] = useState('');
  const item = items.find(i => i.id === f.itemId), bal = have(f.storeId, f.itemId);
  const parties = f.dir === 'out' ? [...s.farm.groups.map(g => g.name), ...stores.filter(x => x.id !== f.storeId).map(x => `${x.code} ${x.name}`)] : [];
  const save = () => {
    const qty = Number(f.qty);
    if (!(qty > 0)) return setErr('Enter a quantity above 0.');
    if (f.dir === 'out' && qty > bal) return setErr(`Only ${qtyOf(bal, item?.unit ?? '')} in this store.`);
    const m: StockMove = { id: newId('mv'), storeId: f.storeId, itemId: f.itemId, date: f.date, dir: f.dir, qty, party: f.party.trim(), orderId: '', by: s.session?.user.id ?? '', note: f.note.trim() };
    farmChange({ op: 'upsert', kind: 'move', item: m });
    onSaved(`${f.dir === 'in' ? 'Received' : 'Issued'} ${qtyOf(qty, item?.unit ?? '')} ${item?.name.toLowerCase() ?? ''}. Balance now ${qtyOf(bal + (f.dir === 'in' ? qty : -qty), item?.unit ?? '')}.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">{f.dir === 'in' ? 'Into store' : 'Out of store'}</h2>
      <Seg items={[['in', 'In'], ['out', 'Out']]} value={f.dir} onPick={v => setF({ ...f, dir: v as 'in' | 'out', party: '' })} />
      <Field label="Store"><select className="input" value={f.storeId} onChange={e => setF({ ...f, storeId: e.target.value })}>{stores.map(x => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></Field>
      <Field label="Item"><select className="input" value={f.itemId} onChange={e => setF({ ...f, itemId: e.target.value })}>{items.map(i => <option key={i.id} value={i.id}>{i.code} · {i.name}</option>)}</select></Field>
      <div className="sub">In store now: {qtyOf(bal, item?.unit ?? '')}</div>
      <div className="grid2">
        <Field label="Date"><input className="input" type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} /></Field>
        <Field label={`Quantity (${item?.unit ?? ''})`}><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
      </div>
      <Field label={f.dir === 'in' ? 'From (supplier, donor, harvest…)' : 'Issued to'}>
        {parties.length ? <><input className="input" list="parties" value={f.party} onChange={e => setF({ ...f, party: e.target.value })} /><datalist id="parties">{parties.map(p => <option key={p} value={p} />)}</datalist></>
          : <input className="input" value={f.party} onChange={e => setF({ ...f, party: e.target.value })} placeholder={f.dir === 'in' ? 'e.g. opening count, FAO, harvest' : ''} />}
      </Field>
      <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Save" />
    </div>
  );
}

function OrderForm({ stores, items, storeId, itemId, qty, onCancel, onSaved }: { stores: StoreT[]; items: StockItem[]; storeId: string; itemId: string; qty: number; onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp(), place = usePlace();
  const [f, setF] = useState({ itemId, qty: qty ? String(qty) : '', storeId, supplier: '', where: '' });
  const [err, setErr] = useState('');
  const item = items.find(i => i.id === f.itemId);
  const save = () => {
    if (!(Number(f.qty) > 0)) return setErr('Enter a quantity above 0.');
    const o = newOrder(f.itemId, Number(f.qty), f.storeId, f.supplier.trim(), s.session?.user.id ?? '', f.where.trim() || place.payam);
    farmChange({ op: 'upsert', kind: 'order', item: o });
    onSaved(`Order ${o.code} requested: ${qtyOf(o.qty, item?.unit ?? '')} ${item?.name.toLowerCase() ?? ''}.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New order</h2>
      <Field label="Item"><select className="input" value={f.itemId} onChange={e => setF({ ...f, itemId: e.target.value })}>{items.map(i => <option key={i.id} value={i.id}>{i.code} · {i.name}</option>)}</select></Field>
      <div className="grid2">
        <Field label={`Quantity (${item?.unit ?? ''})`}><input className="input num" type="number" inputMode="decimal" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} /></Field>
        <Field label="Deliver to"><select className="input" value={f.storeId} onChange={e => setF({ ...f, storeId: e.target.value })}>{stores.map(x => <option key={x.id} value={x.id}>{x.code}</option>)}</select></Field>
      </div>
      <Field label="Supplier (if known)"><input className="input" value={f.supplier} onChange={e => setF({ ...f, supplier: e.target.value })} /></Field>
      <Field label="Where is it now"><input className="input" value={f.where} onChange={e => setF({ ...f, where: e.target.value })} placeholder={place.payam} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Request" />
    </div>
  );
}

function StatusForm({ order, item, onCancel, onSaved }: { order: Order; item?: StockItem; onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp();
  const [status, setStatus] = useState<OrderStatus>(order.status);
  const [where, setWhere] = useState(order.where);
  const [note, setNote] = useState('');
  const [got, setGot] = useState(String(order.qty));
  const closed = order.status === 'received' || order.status === 'cancelled';
  const save = () => {
    const at = new Date().toISOString(), by = s.session?.user.id ?? '';
    const next: Order = { ...order, status, where: where.trim(), history: [...order.history, { at, status, where: where.trim(), by, note: note.trim() }] };
    const ops: Parameters<typeof farmChange> = [{ op: 'upsert', kind: 'order', item: next }];
    // Receiving an order puts the stock into its store.
    if (status === 'received' && Number(got) > 0) ops.push({ op: 'upsert', kind: 'move', item: { id: newId('mv'), storeId: order.storeId, itemId: order.itemId, date: at.slice(0, 10), dir: 'in', qty: Number(got), party: order.supplier || 'order', orderId: order.id, by, note: note.trim() } });
    farmChange(...ops);
    onSaved(`Order ${order.code}: ${status}${where.trim() ? `, at ${where.trim()}` : ''}.${status === 'received' ? ` ${qtyOf(Number(got), item?.unit ?? '')} added to the store.` : ''}`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">{order.code}</h2>
      <div className="sub">{item?.name} · {qtyOf(order.qty, item?.unit ?? '')} · deliver to {order.storeId}{order.supplier ? ` · ${order.supplier}` : ''}</div>
      <div style={{ borderTop: '1px solid var(--color-divider)' }}>
        {order.history.map((h, i) => (
          <div key={i} className="rowg" style={{ padding: '7px 0' }}>
            <span><span style={{ display: 'block', fontSize: 13.5 }}>{h.status}{h.where ? ` · ${h.where}` : ''}</span>{h.note && <span className="sub">{h.note}</span>}</span>
            <span className="sub num">{new Date(h.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · {h.by}</span>
          </div>
        ))}
      </div>
      {closed ? <div className="note">This order is {order.status}.</div> : <>
        <Field label="New status"><select className="input" value={status} onChange={e => setStatus(e.target.value as OrderStatus)}>{ORDER_STATUS.map(x => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Where is it now"><input className="input" value={where} onChange={e => setWhere(e.target.value)} placeholder="e.g. Bor, on the road, Juba warehouse" /></Field>
        {status === 'received' && <Field label={`Quantity received (${item?.unit ?? ''})`}><input className="input num" type="number" value={got} onChange={e => setGot(e.target.value)} /></Field>}
        <Field label="Note"><input className="input" value={note} onChange={e => setNote(e.target.value)} /></Field>
      </>}
      {closed ? <button className="btn plain" onClick={onCancel}>Back</button> : <Buttons onCancel={onCancel} onSave={save} label="Update" />}
    </div>
  );
}

function StoreForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string, id: string) => void }) {
  const s = useApp(), place = usePlace();
  const n = (s.farm.stores ?? []).length + 1;
  const [f, setF] = useState({ code: `ST-${String(n).padStart(2, '0')}`, name: '', place: place.payam, keeper: '' });
  const [err, setErr] = useState('');
  const save = () => {
    if (!f.code.trim() || !f.name.trim()) return setErr('Store ID and name are required.');
    if ((s.farm.stores ?? []).some(x => x.code.toLowerCase() === f.code.trim().toLowerCase())) return setErr('That store ID is already used.');
    const st: StoreT = { id: f.code.trim(), code: f.code.trim(), name: f.name.trim(), place: f.place.trim(), keeper: f.keeper.trim() };
    farmChange({ op: 'upsert', kind: 'store', item: st });
    onSaved(`Store ${st.code} added.`, st.id);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New store</h2>
      <div className="grid2"><Field label="Store ID"><input className="input" value={f.code} onChange={e => setF({ ...f, code: e.target.value })} /></Field><Field label="Name"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field></div>
      <Field label="Place"><input className="input" value={f.place} onChange={e => setF({ ...f, place: e.target.value })} /></Field>
      <Field label="Store keeper"><input className="input" value={f.keeper} onChange={e => setF({ ...f, keeper: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Add store" />
    </div>
  );
}

function ItemForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (m: string) => void }) {
  const s = useApp();
  const [f, setF] = useState({ code: '', name: '', unit: 'kg', kind: 'seed' as StockItem['kind'], reorder: '' });
  const [err, setErr] = useState('');
  const save = () => {
    if (!f.code.trim() || !f.name.trim()) return setErr('Item ID and name are required.');
    if ((s.farm.items ?? []).some(x => x.code.toLowerCase() === f.code.trim().toLowerCase())) return setErr('That item ID is already used.');
    const it: StockItem = { id: f.code.trim().toUpperCase(), code: f.code.trim().toUpperCase(), name: f.name.trim(), unit: f.unit.trim() || 'pcs', kind: f.kind, reorder: f.reorder ? Number(f.reorder) : null };
    farmChange({ op: 'upsert', kind: 'item', item: it });
    onSaved(`Item ${it.code} added.`);
  };
  return (
    <div className="pad g12" style={{ paddingTop: 14 }}>
      <h2 className="h2 h20">New item</h2>
      <div className="grid2"><Field label="Item ID"><input className="input" value={f.code} onChange={e => setF({ ...f, code: e.target.value })} placeholder="e.g. SEED-MAIZ" /></Field><Field label="Name"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field></div>
      <div className="grid2">
        <Field label="Unit"><input className="input" value={f.unit} onChange={e => setF({ ...f, unit: e.target.value })} /></Field>
        <Field label="Type"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value as StockItem['kind'] })}>{['seed', 'input', 'tool', 'packaging', 'other'].map(k => <option key={k}>{k}</option>)}</select></Field>
      </div>
      <Field label="Needed in store (warn below)"><input className="input num" type="number" value={f.reorder} onChange={e => setF({ ...f, reorder: e.target.value })} /></Field>
      {err && <div className="msg">{err}</div>}
      <Buttons onCancel={onCancel} onSave={save} label="Add item" />
    </div>
  );
}
