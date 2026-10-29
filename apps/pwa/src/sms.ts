// Messages that leave from the phone itself: SMS from its SIM, email from its mail app, WhatsApp from its WhatsApp.
// The app fills in the recipients and text; the person presses Send.
export const smsLink = (numbers: string[], body: string) => `sms:${numbers.join(',')}?body=${encodeURIComponent(body)}`;
// Everyone in bcc so subscribers do not see each other's addresses.
export const mailLink = (bcc: string[], subject: string, body: string) => `mailto:?bcc=${bcc.map(encodeURIComponent).join(',')}&subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
// wa.me with text opens WhatsApp's chat picker with the text filled in; the person picks the group.
export const whatsappShare = (body: string) => `https://wa.me/?text=${encodeURIComponent(body)}`;

export const openLink = (href: string) => { const a = document.createElement('a'); a.href = href; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove(); };

export async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}
