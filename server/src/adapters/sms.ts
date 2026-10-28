import { cfg, need } from '../config';

export interface SendResult { to: string; ok: boolean; detail: string }

export async function sendSms(to: string[], message: string): Promise<SendResult[]> {
  need('sms');
  if (cfg.smsProvider === 'africastalking') {
    const res = await fetch('https://api.africastalking.com/version1/messaging', {
      method: 'POST',
      headers: { apiKey: cfg.smsKey, accept: 'application/json', 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: cfg.smsUser, to: to.join(','), message, ...(cfg.smsSender ? { from: cfg.smsSender } : {}) })
    });
    if (!res.ok) throw new Error(`Africa's Talking → ${res.status} ${await res.text()}`);
    const j = await res.json() as { SMSMessageData: { Recipients: { number: string; status: string }[] } };
    return j.SMSMessageData.Recipients.map(r => ({ to: r.number, ok: r.status === 'Success', detail: r.status }));
  }
  if (cfg.smsProvider === 'twilio') {
    const auth = Buffer.from(`${cfg.smsUser}:${cfg.smsKey}`).toString('base64');
    return Promise.all(to.map(async n => {
      const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${cfg.smsUser}/Messages.json`, {
        method: 'POST', headers: { authorization: `Basic ${auth}`, 'content-type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ To: n, From: cfg.smsSender, Body: message })
      });
      return { to: n, ok: res.ok, detail: res.ok ? 'queued' : `${res.status}` };
    }));
  }
  if (cfg.smsProvider === 'smsgate') {
    // SMSGate (sms-gate.app): an Android phone sends the texts, as in the altimetry-nightly pipeline.
    const auth = Buffer.from(`${cfg.smsUser}:${cfg.smsKey}`).toString('base64');
    const res = await fetch(`${cfg.smsApiUrl}/messages`, {
      method: 'POST', headers: { authorization: `Basic ${auth}`, 'content-type': 'application/json' },
      body: JSON.stringify({ textMessage: { text: message }, phoneNumbers: to })
    });
    const ok = res.ok, detail = ok ? 'queued on gateway phone' : `${res.status}`;
    return to.map(n => ({ to: n, ok, detail }));
  }
  throw new Error(`Unknown SMS_PROVIDER "${cfg.smsProvider}" (use smsgate, africastalking or twilio)`);
}

// Inbound webhooks: Africa's Talking posts from/text, Twilio posts From/Body,
// SMSGate posts JSON {event: 'sms:received', payload: {phoneNumber, message}}.
export function parseInbound(body: Record<string, unknown>) {
  const p = (body.payload ?? {}) as Record<string, string>;
  const f = body as Record<string, string>;
  return { from: f.from || f.From || p.phoneNumber || '', text: f.text || f.Body || p.message || '' };
}
