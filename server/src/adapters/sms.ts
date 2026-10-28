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
  throw new Error(`Unknown SMS_PROVIDER "${cfg.smsProvider}" (use africastalking or twilio)`);
}

// Inbound webhooks: Africa's Talking posts from/text, Twilio posts From/Body.
export function parseInbound(form: Record<string, string>) {
  return { from: form.from || form.From || '', text: form.text || form.Body || '' };
}
