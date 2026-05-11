## ❌ Why Emails Sent via Reply Draft Agent Don't Appear in Gmail/Hostinger Sent Folder

### The Problem (with your setup: sales@laskontech.com via Hostinger)

Emails sent through the Reply Draft Agent appear in the app's Sent tab **BUT NOT** in your actual Gmail/Hostinger Sent folder because:

---

## 🔍 Root Causes

### **1. IMAP Sync Not Pulling from Sent Folder**

**Status:** ⚠️ **This is likely the issue for you**

- The IMAP sync (`sync_inbox` command) only fetches the **Sent folder** when:
  - ✅ `is_reply_agent_account = True` (your account should have this)
  - ✅ `enable_imap_sync = True` (check this in EmailAccount settings)
  - ✅ The Sent folder can be **found via IMAP**

**For Hostinger**, the Sent folder names are usually:
- `Sent` (default)
- `Sent Items`
- `Sent Mail`  
- `INBOX.Sent`

If your Hostinger mailbox uses a **different folder name or locale** (e.g., Spanish/Arabic), the sync won't find it.

**📋 Diagnostic Command:**
```bash
python manage.py sync_inbox --account-id <ACCOUNT_ID> --dry-run
```

Look for:
```
Sent folder detected: "Sent"    # ✅ Good
```
OR
```
[INFO] Sent folder not found via common names; skipping sent sync   # ❌ Problem
```

---

### **2. IMAP Not Enabled for Your Account**

**Check EmailAccount settings:**

1. Go to Marketing Agent → Email Accounts
2. Select `sales@laskontech.com`
3. Verify:
   - ✅ `enable_imap_sync = True` (checkbox enabled)
   - ✅ IMAP credentials filled (host, username, password)
   - ✅ `is_reply_agent_account = True` (should be set when you connected it)

If `enable_imap_sync` is **False**, the sync won't run at all.

---

### **3. SMTP ≠ IMAP Account Mismatch**

Your **SMTP settings** (for sending) might be different from your **IMAP settings** (for receiving):

```
SMTP: smtp.hostinger.com:587  ← Sending goes OUT here
IMAP: imap.hostinger.com:993  ← But app only syncs INBOX from here
```

If the SMTP and IMAP usernames don't match, Hostinger might not link the sent message to your mailbox properly.

**Verify in Hostinger:**
- SMTP Username: `sales@laskontech.com`
- IMAP Username: `sales@laskontech.com` (must be same)

---

## ✅ Solutions

### **Option 1: Enable IMAP Sync (Recommended)**

If `enable_imap_sync` is currently **False**:

1. Open your EmailAccount (`sales@laskontech.com`)
2. Toggle: `enable_imap_sync = True`
3. Ensure IMAP credentials are filled
4. Save
5. Run: `python manage.py sync_inbox --account-id <ACCOUNT_ID>`
6. New sent emails will appear within 5 minutes

**Code flow when enabled:**
```
send_approved() 
  → mirror_sent_to_inbox() [INSTANT, shows in app Sent tab]
  → IMAP sync (5 min later) [pulls from server Sent folder]
```

---

### **Option 2: Add Hostinger-Specific Sent Folder Names**

If Hostinger uses a non-standard Sent folder name, we need to add it to the detection list:

**File:** [marketing_agent/management/commands/sync_inbox.py](marketing_agent/management/commands/sync_inbox.py#L422)

Currently checks:
```python
SENT_FOLDER_NAMES = [
    '[Gmail]/Sent Mail',      # Gmail
    'Sent',                    # Generic IMAP / Hostinger
    'Sent Items',              # Outlook
    'Sent Messages',           # Apple/iCloud
    'INBOX.Sent',              # Courier IMAP
    'Sent Mail',               # Older format
]
```

**To add Hostinger-specific variants:**

If your Hostinger Sent folder is named differently (e.g., localized), we can add it. First, **check Hostinger's webmail** to see the exact folder name, then I'll add it to the list.

---

### **Option 3: Force Sync from Command Line**

Test sending manually and force a full sync:

```bash
# Manually run sync for your account
python manage.py sync_inbox --account-id 1 --verbose

# Check if Sent folder is detected
# Output should say: "Sent folder detected: 'Sent'" ✅
```

If it says **not found**, Hostinger's folder name is different from the hardcoded list.

---

### **Option 4: Ask Hostinger Support**

Ask them the exact IMAP folder names for:
- Inbox: (usually stays `INBOX`)
- Sent: `?` (this is what we need to know)

Hostinger might use regional localization:
- Spanish: `Enviados`
- French: `Éléments envoyés`
- Arabic: `الرسائل المرسلة`
- Etc.

---

## 🔧 How It Works (Current Architecture)

### When You Send an Email:

```
1. User clicks "Send" on a draft
   ↓
2. send_approved() calls email_service.send_raw_email()
   ↓
3. Email sent via SMTP to recipient
   ↓
4. _mirror_sent_to_inbox() creates a LOCAL InboxEmail row 
   (direction='out') immediately
   ↓
5. ✅ Email appears in app's Sent tab INSTANTLY
   ↓
6. IMAP sync runs (every 5 minutes)
   ↓
7. Fetches from Hostinger's Sent folder (if found)
   ↓
8. ✅ Email also appears in actual Gmail/Hostinger
```

**The gap:** If IMAP Sent sync is disabled or the folder isn't found, step 7-8 never happen, so the email is **only in the app**, not on the server.

---

## 🧪 Quick Checklist

- [ ] `enable_imap_sync = True` on EmailAccount?
- [ ] IMAP host, username, password filled for Hostinger?
- [ ] `is_reply_agent_account = True` on the account?
- [ ] Run sync: `python manage.py sync_inbox --account-id <ID>`
- [ ] Check output for: `Sent folder detected:`?
- [ ] Verify SMTP and IMAP usernames match in Hostinger?
- [ ] Check Hostinger's actual Sent folder name in webmail UI?

---

## 📞 Next Steps

Let me know:
1. **Is `enable_imap_sync` currently True or False** on your account?
2. **What does the sync output say?** (Run the command above)
3. **What's the exact Sent folder name in Hostinger's webmail?**

Once I have this info, I can either:
- ✅ Enable sync if it's disabled
- ✅ Add Hostinger's folder name if it's non-standard
- ✅ Debug connection issues if IMAP credentials are wrong
