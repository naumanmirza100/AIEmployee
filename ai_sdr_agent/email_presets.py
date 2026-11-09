"""Ready-made email templates, one per kind of industry, for the Email Templates tab: a starting point the user opens
in the editor, fills in and saves as their own (the originals here never change).

What the sender offers is theirs to say, so each has a few parts in square brackets starting with "Your" —
[Your offer in one sentence], [Your booking link] — which ai_sdr_agent/email_templates.py will not let go out
unfilled. Everything else is ready: the lead and sender variables, an unsubscribe link, and a layout that holds up in
Gmail, Outlook and on phones (tables, inline styles, no images).
"""


def _layout(*, accent: str, tint: str, preheader: str, eyebrow: str, headline: str, intro: str, points: list,
            closing: str, button: str) -> str:
    rows = ''.join(f'''
                  <tr>
                    <td valign="top" style="padding:0 12px 14px 0;width:22px;">
                      <div style="width:22px;height:22px;border-radius:11px;background:{accent};color:#ffffff;
                                  font-size:12px;font-weight:700;line-height:22px;text-align:center;">{n}</div>
                    </td>
                    <td valign="top" style="padding:0 0 14px;color:#374151;font-size:15px;line-height:1.6;">
                      <strong style="color:#111827;">{title}</strong><br/>{text}
                    </td>
                  </tr>''' for n, (title, text) in enumerate(points, 1))
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light" />
  <title>{{sender_company}}</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;">
  <div style="display:none;max-height:0;overflow:hidden;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f5f7;">
    <tr>
      <td align="center" style="padding:32px 12px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;background:#ffffff;border:1px solid #e7e8ec;border-radius:14px;
                      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
          <tr>
            <td style="background:{accent};border-radius:14px 14px 0 0;padding:22px 36px;">
              <span style="color:#ffffff;font-size:13px;font-weight:700;letter-spacing:0.08em;
                           text-transform:uppercase;">{{sender_company}}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:32px 36px 8px;">
              <p style="margin:0 0 10px;color:{accent};font-size:12px;font-weight:700;letter-spacing:0.06em;
                        text-transform:uppercase;">{eyebrow}</p>
              <h1 style="margin:0 0 18px;color:#111827;font-size:24px;line-height:1.3;font-weight:700;">{headline}</h1>
              <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.7;">Hi {{first_name}},</p>
              <p style="margin:0 0 22px;color:#374151;font-size:15px;line-height:1.7;">{intro}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:0 36px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:{tint};border-radius:10px;">
                <tr><td style="padding:20px 20px 6px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}
                  </table>
                </td></tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 36px 8px;">
              <p style="margin:0 0 22px;color:#374151;font-size:15px;line-height:1.7;">{closing}</p>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr><td style="background:{accent};border-radius:8px;">
                  <a href="[Your booking link]" target="_blank"
                     style="display:inline-block;padding:13px 26px;color:#ffffff;font-size:15px;font-weight:600;
                            text-decoration:none;">{button}</a>
                </td></tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 36px 32px;">
              <p style="margin:0;padding-top:20px;border-top:1px solid #eeeff2;color:#374151;font-size:14px;line-height:1.6;">
                Best regards,<br/>
                <strong style="color:#111827;">{{sender_name}}</strong><br/>
                <span style="color:#6b7280;">{{sender_title}}, {{sender_company}}</span>
              </p>
            </td>
          </tr>
        </table>
        <p style="margin:18px 0 0;max-width:560px;color:#9ca3af;font-size:12px;line-height:1.6;
                  font-family:Helvetica,Arial,sans-serif;">
          You're receiving this because {{company_name}} may find it useful.
          <a href="{{unsubscribe_url}}" style="color:#6b7280;">Unsubscribe</a>
        </p>
      </td>
    </tr>
  </table>
</body>
</html>'''


PRESETS = [
    {
        'key': 'dental_medical',
        'accent': '#0f766e',
        'name': 'Dental & medical practices',
        'industries': ['Medical Practice', 'Hospital & Health Care', 'Dentistry', 'Health, Wellness & Fitness'],
        'description': 'For clinics and practices: calm teal, a three-point reason to talk, and a call to book.',
        'subject': 'A quick idea for {company_name}',
        'html': _layout(
            accent='#0f766e', tint='#f0fdfa',
            preheader='Three ways practices like yours keep their diary full.',
            eyebrow='For practice owners',
            headline='More booked appointments, less time on the phone',
            intro=('Running a practice like {company_name} means juggling patients, staff and an ever-ringing phone. '
                   '[Your offer in one sentence — what you do for practices like theirs.]'),
            points=[
                ('Fewer missed enquiries', '[Your first benefit — e.g. how patients reach the practice out of hours.]'),
                ('A fuller diary', '[Your second benefit — e.g. fewer no-shows or faster rebooking.]'),
                ('Time back for your team', '[Your third benefit — e.g. less admin at reception.]'),
            ],
            closing=('Would a 15-minute call next week be useful to see whether it fits {company_name}? '
                     'No pressure either way.'),
            button='Book a 15-minute call',
        ),
    },
    {
        'key': 'education',
        'accent': '#1e3a8a',
        'name': 'Schools, colleges & universities',
        'industries': ['Education', 'Higher Education', 'Primary/Secondary Education', 'E-Learning',
                       'Education Management'],
        'description': 'For education leaders: a trustworthy navy layout built around students and staff time.',
        'subject': '{first_name}, an idea for {company_name}',
        'html': _layout(
            accent='#1e3a8a', tint='#eff6ff',
            preheader='How institutions like yours give staff time back for students.',
            eyebrow='For education leaders',
            headline='Give your staff more time for what matters most',
            # Not "leaders tell us": no claim of conversations the sender may never have had.
            intro=('At an institution like {company_name}, there is rarely enough time for students. '
                   '[Your offer in one sentence — what you do for schools, colleges or universities.]'),
            points=[
                ('Less admin for staff', '[Your first benefit — e.g. what it takes off teachers\' plates.]'),
                ('Better outcomes for students', '[Your second benefit — e.g. engagement, attendance or results.]'),
                ('Simple to start', '[Your third benefit — e.g. how quickly a department can get going.]'),
            ],
            closing=('If it would help, I can walk you through it in a short call — and send a one-page summary '
                     'you can share with colleagues at {company_name}.'),
            button='Arrange a short call',
        ),
    },
    {
        'key': 'real_estate',
        'accent': '#9a3412',
        'name': 'Real estate agencies',
        'industries': ['Real Estate', 'Commercial Real Estate', 'Property Management'],
        'description': 'For agents and property firms: a warm, confident layout focused on listings and leads.',
        'subject': 'More instructions for {company_name}?',
        'html': _layout(
            accent='#9a3412', tint='#fff7ed',
            preheader='How agencies like yours win more instructions without more cold calls.',
            eyebrow='For estate agents & property firms',
            headline='Win more instructions without more cold calls',
            intro=('In a busy market, agencies like {company_name} win on speed and follow-up. '
                   '[Your offer in one sentence — what you do for agents and property firms.]'),
            points=[
                ('Every enquiry answered fast', '[Your first benefit — e.g. how buyers and sellers hear back sooner.]'),
                ('More valuations booked', '[Your second benefit — e.g. how more leads turn into appointments.]'),
                ('A clearer pipeline', '[Your third benefit — e.g. what your team can see and act on.]'),
            ],
            closing=('Worth a quick chat to see whether it would work for {company_name}? '
                     'Fifteen minutes is plenty.'),
            button='Pick a time to talk',
        ),
    },
]
