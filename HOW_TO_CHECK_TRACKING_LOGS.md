# 📊 Email Tracking Logs - Kaise Check Karein

## 🎯 Logs Kahan Milenge?

### 1. **Console/Terminal (Sabse Aasan)**
Agar aap `python manage.py runserver` se server chalate hain, to **terminal/command prompt** mein sab logs dikhenge:

```
[EMAIL TRACKING] Processing link: <a href="#m_..."...
[EMAIL TRACKING] Found anchor link (href='#m_...') - converting to campaign page
[EMAIL TRACKING] Converted anchor link: #m_... -> /marketing/campaigns/1/
[EMAIL TRACKING] Wrapping link: /marketing/campaigns/1/ -> https://yourserver.com/token?t=abc123&url=...
[SIMPLE OPEN TRACK] Token: abc123..., Email: user@example.com, Current Status: sent
✅ [SIMPLE TRACK UPDATED] Email: user@example.com, Status: sent → opened
[SIMPLE CLICK TRACK] Token: abc123..., Email: user@example.com, Current Status: opened
✅ [SIMPLE CLICK UPDATED] Email: user@example.com, Status: opened → clicked
```

**Kahan dekhein:**
- Jis terminal/command prompt mein `python manage.py runserver` chala rahe hain, wahi pe sab logs dikhenge
- Real-time tracking: Jab bhi koi email open ya click karega, immediately logs dikhenge

---

### 2. **Log File (Permanent Record)**
Ab sab tracking logs ek file mein save honge:

**File Location:**
```
D:\University\work\AI_Employyes\AIEmployee\logs\marketing_tracking.log
```

**Kaise dekhein:**
1. **Windows Explorer** mein jao: `D:\University\work\AI_Employyes\AIEmployee\logs\`
2. `marketing_tracking.log` file open karo (Notepad, VS Code, ya koi bhi text editor se)
3. Sabse neeche latest logs honge

**Ya Command Prompt se:**
```cmd
cd D:\University\work\AI_Employyes\AIEmployee\logs
type marketing_tracking.log
```

**Ya last 50 lines dekhein:**
```cmd
powershell Get-Content marketing_tracking.log -Tail 50
```

---

### 3. **Real-time Log Monitoring (Advanced)**
Agar aap real-time dekhte rehna chahte hain:

**Windows PowerShell:**
```powershell
Get-Content D:\University\work\AI_Employyes\AIEmployee\logs\marketing_tracking.log -Wait -Tail 20
```

**Ya VS Code mein:**
1. `logs/marketing_tracking.log` file open karo
2. File ko "Watch" mode mein rakho (auto-refresh)

---

## 🔍 Kya Dekhna Hai?

### Email Open Tracking:
```
[SIMPLE OPEN TRACK] Token: abc123..., Email: user@example.com
✅ [SIMPLE TRACK UPDATED] Email: user@example.com, Status: sent → opened
```

### Email Click Tracking:
```
[SIMPLE CLICK TRACK] Token: abc123..., Email: user@example.com
✅ [SIMPLE CLICK UPDATED] Email: user@example.com, Status: opened → clicked
[SIMPLE CLICK TRACK] Redirecting to: https://yourserver.com/marketing/campaigns/1/
```

### Link Processing (Email Send Time):
```
[EMAIL TRACKING] Processing link: <a href="#m_..."...
[EMAIL TRACKING] Found anchor link (href='#m_...') - converting to campaign page
[EMAIL TRACKING] Converted anchor link: #m_... -> /marketing/campaigns/1/
[EMAIL TRACKING] Wrapping link: /marketing/campaigns/1/ -> https://yourserver.com/token?t=abc123&url=...
```

---

## ⚠️ Agar Logs Nahi Dikhein:

1. **Check karo ki server chal raha hai:**
   ```cmd
   python manage.py runserver
   ```

2. **Log file create hui hai ya nahi:**
   ```cmd
   dir D:\University\work\AI_Employyes\AIEmployee\logs\marketing_tracking.log
   ```

3. **Agar file nahi hai, manually create karo:**
   - `logs` folder mein jao
   - `marketing_tracking.log` file create karo (empty file)

4. **Permissions check karo:**
   - File/folder pe write permissions honi chahiye

---

## 📝 Quick Test:

1. **Email send karo** (test email bhi chalega)
2. **Terminal/Console dekho** - email send time pe logs dikhenge
3. **Email open karo** - open tracking log dikhega
4. **Link click karo** - click tracking log dikhega
5. **Log file check karo** - sab permanent record mein save hoga

---

## 💡 Tips:

- **Terminal logs** = Real-time, immediate feedback
- **Log file** = Permanent record, baad mein review karne ke liye
- **Search in logs**: `[EMAIL TRACKING]` ya `[SIMPLE` search karo to quickly find tracking events
- **Filter logs**: Specific email ya token search karo to track specific user

---

**Ab aap easily tracking logs check kar sakte hain! 🎉**

