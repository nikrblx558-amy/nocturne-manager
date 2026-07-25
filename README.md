# Nocturne Manager

Bot Discord dengan 2 fitur utama:

1. **Join/Leave Notifications** — panel builder interaktif (tombol + live preview) buat custom embed tanpa perlu edit kode. Bisa juga set teks sambutan di luar embed.
2. **Application System** — sistem form aplikasi (staff application, whitelist, dll) lengkap dengan panel builder live-preview, tombol Apply persisten, modal pertanyaan custom, dan review Accept/Deny di channel log.

> 📌 Catatan bahasa: **semua teks yang dikirim bot ke user** (embed, tombol, pesan error, dll) sengaja dibikin **full English**, biar bot ini rapi dipakai di server internasional. README ini sendiri tetap Bahasa Indonesia karena ini dokumentasi buat kamu sebagai developer, bukan teks yang dikirim bot.

Dibangun pakai `discord.py` 2.x, mendukung **slash command** dan **prefix command klasik**, siap deploy ke **Railway**.

---

## 1. Setup Bot di Discord Developer Portal

1. Buka https://discord.com/developers/applications → **New Application** → beri nama `Nocturne Manager`.
2. Tab **Bot** → klik **Reset Token**, simpan token itu (jangan disebar).
3. Di tab **Bot**, scroll ke bagian **Privileged Gateway Intents**, aktifkan DUA-DUANYA:
   - **SERVER MEMBERS INTENT** — wajib, dipakai buat deteksi join/leave.
   - **MESSAGE CONTENT INTENT** — wajib, dipakai buat prefix command (`n!...`). **Ini yang paling sering kelupaan** — kalau prefix command gak respon sama sekali padahal kodenya udah bener, 99% karena toggle ini belum diaktifin/di-save di sini.
4. Tab **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `View Channels`
   - Buka link yang dihasilkan buat invite bot ke server kamu.

---

## 2. Install & Jalankan Lokal

```bash
git clone <repo-lu>
cd nocturne-manager
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Isi `.env`:

```
DISCORD_TOKEN=isi_token_bot_disini
GUILD_ID=isi_id_server_testing_disini   # opsional, biar slash command instan
PREFIX=n!                               # prefix untuk command klasik
```

Jalankan:

```bash
python main.py
```

Begitu bot online, cek dulu di server tester:
- Ketik `n!ping` di channel manapun — kalau bot balas `🏓 Pong! Prefix commands are working.`, berarti prefix command + Message Content Intent sudah benar.
- Kalau `n!ping` gak ada respon sama sekali, balik ke Langkah 1 poin 3 — pasti Message Content Intent belum kesave.

---

## 3. Deploy ke Railway

1. Push project ini ke GitHub repo baru.
2. Di Railway: **New Project → Deploy from GitHub repo** → pilih repo ini.
3. Railway otomatis detect `Procfile` (`worker: python main.py`) — pastikan service dijalankan sebagai **worker**, bukan web (karena bot Discord tidak butuh port HTTP).
4. Masuk ke tab **Variables**, tambahkan:
   - `DISCORD_TOKEN` = token bot kamu
   - `GUILD_ID` = (opsional, hapus/skip kalau mau slash command global di semua server)
   - `PREFIX` = (opsional, default `n!`)
5. Deploy. Cek log — kalau muncul `Logged in as Nocturne Manager (ID: ...)` berarti sukses. Log juga bakal nampilin baris `Prefix commands active with prefix: 'n!' (message_content intent: True)` — kalau `intent: True` tapi tetep gak respon di Discord, itu tandanya masalahnya di toggle Developer Portal, bukan di kode.

> ⚠️ Data `data/*.json` disimpan di filesystem container. Railway punya ephemeral filesystem by default — kalau redeploy, data ikut ke-reset. Kalau mau data join/leave & aplikasi persisten, tambahkan **Railway Volume** dan mount ke folder `data/`.

---

## 4. Cara Pakai — Join/Leave

**Slash command:**

| Command | Fungsi |
|---|---|
| `/joinleave builder type:Join` | Buka panel builder untuk embed **Join** (live preview, hanya kamu yang lihat) |
| `/joinleave builder type:Leave` | Buka panel builder untuk embed **Leave** |
| `/joinleave toggle type:Join enabled:True/False` | Aktif/nonaktifkan cepat tanpa buka builder |
| `/joinleave test type:Join` | Kirim contoh embed ke channel yang sudah diset (pakai data kamu sendiri) |

**Prefix command** (default prefix `n!`, bisa diubah lewat env `PREFIX`):

| Command | Fungsi |
|---|---|
| `n!joinleave builder join` / `n!joinleave builder leave` | Buka panel builder (publik di channel, tombolnya tetap cuma bisa dipakai kamu) |
| `n!joinleave toggle join on` / `n!joinleave toggle leave off` | Aktif/nonaktifkan cepat |
| `n!joinleave test join` | Kirim contoh embed |

Semua command ini butuh izin **Manage Server**.

**Tombol di dalam Panel Builder:**

- 📝 **Title** — judul embed
- 📄 **Description** — deskripsi (bisa pakai variabel)
- 🖼️ **Thumbnail** — gambar kecil pojok kanan atas (bisa `{user_avatar}`)
- 🏳️ **Banner** — gambar besar di bawah embed
- 🎨 **Color** — warna embed (hex, contoh `#8B0000`, bebas diganti)
- ➕ **Field** — tambah field biasa (nama, isi, inline)
- 🔸 **Icon Field** — field dengan emoji di depan namanya
- ➖ **Separator** — garis pembatas tipis
- 🔗 **Row Link** — tombol link di bawah embed (maks 5)
- 🧩 **Variable** — daftar variabel yang bisa dipakai
- 🗑️ dropdown **Remove field/separator**
- 📌 dropdown **Set channel**
- 💬 **Greeting** — teks yang dikirim **di luar embed** (di atas embed)
- 🔻 **Footer** — teks footer custom embed
- 🔌 **Enable/Disable**
- ♻️ **Reset**
- ✅ **Done**

**Variabel yang tersedia:**

```
{user}            mention user
{user_name}       username
{user_display}    nickname
{user_id}         ID user
{user_avatar}     link avatar user
{user_created}    tanggal akun dibuat
{server}          nama server
{server_icon}     link icon server
{member_count}    jumlah member sekarang
{date}            tanggal hari ini
{time}            jam sekarang
```

---

## 5. Cara Pakai — Application System

Sistem ini gantiin fitur Status Bot yang lama. Konsepnya: kamu bikin satu atau lebih **panel aplikasi** (misal "Staff Application", "Partnership Request", dll), atur pertanyaannya lewat builder, publish ke sebuah channel — nanti muncul embed dengan tombol **Apply**. User klik tombol itu → muncul form (modal) sesuai pertanyaan yang kamu set → jawaban otomatis terkirim ke channel log kamu sebagai embed dengan tombol **Accept/Deny**. Begitu staff klik Accept/Deny, status ke-update di embed dan si applicant otomatis di-DM hasilnya.

**Slash command:**

| Command | Fungsi |
|---|---|
| `/application new name:"Staff Application"` | Bikin panel aplikasi baru |
| `/application builder panel:<pilih>` | Buka live-preview builder buat panel itu (autocomplete) |
| `/application list` | Lihat semua panel & status (draft/published) |
| `/application delete panel:<pilih>` | Hapus panel |

**Prefix command:**

| Command | Fungsi |
|---|---|
| `n!application new Staff Application` | Bikin panel baru |
| `n!application builder staff-application` | Buka builder (pakai slug, cek `list` dulu) |
| `n!application list` | Lihat semua panel |
| `n!application delete staff-application` | Hapus panel |

**Tombol di dalam Application Builder:**

- 📝 **Title**, 📄 **Description**, 🖼️ **Thumbnail**, 🏳️ **Banner**, 🎨 **Color** — sama seperti join/leave builder
- 🔻 **Footer** — teks footer custom
- 🔤 **Button Label** — teks tombol Apply (default: "Apply Now")
- 🙂 **Button Emoji** — emoji di tombol Apply (opsional)
- ➕ **Add Question** — tambah pertanyaan (maks **5**, karena limit modal Discord), tiap pertanyaan bisa dipilih gaya jawaban `short` (satu baris) atau `paragraph` (banyak baris)
- 🗑️ dropdown **Remove a question**
- 📌 dropdown **Set log channel** — channel tempat submission direview staff
- 📤 **Publish** — pilih channel tujuan, bot langsung posting panel beneran dengan tombol Apply yang aktif (perlu minimal 1 pertanyaan + log channel sudah diset)
- ♻️ **Reset**, ✅ **Done**

**Poin penting soal Accept/Deny:**
- Tombol Accept/Deny di channel log cuma bisa dipencet staff yang punya izin **Manage Server**.
- Tombol Apply & Accept/Deny **persisten** — tetap berfungsi walau bot restart/redeploy, karena di-handle lewat pengecekan `custom_id` langsung (gak bergantung sama state di memory).
- Kalau applicant nutup DM dari server (privacy setting), notifikasi hasil Accept/Deny gak akan gagal-error, cuma dilewatin diam-diam (bot tetap update embed di channel log).

---

## 6. Struktur Project

```
nocturne-manager/
├── main.py                  # entrypoint bot
├── requirements.txt
├── Procfile                  # start command untuk Railway
├── .env.example
├── cogs/
│   ├── joinleave.py           # listener on_member_join/remove + slash & prefix command
│   ├── panel_builder.py       # View interaktif + semua Modal builder join/leave
│   └── application.py         # Application System: builder, apply modal, decision handling
├── utils/
│   ├── storage.py             # JSON storage atomic (aman dari corrupt saat restart)
│   ├── variables.py           # resolver variabel {user}, {server}, dll
│   └── embed_builder.py       # builder embed join/leave + helper parse_color
└── data/                      # auto-generated: joinleave.json, applications.json
```

---

## 7. Permission yang Dibutuhkan

- Command **join/leave** (`builder`, `toggle`, `test`) butuh izin **Manage Server**.
- Command **application** (`new`, `builder`, `list`, `delete`) butuh izin **Manage Server**.
- Tombol **Accept/Deny** di channel log aplikasi butuh izin **Manage Server** dari staff yang mereview.
- Tombol **Apply** bisa dipencet siapa saja (memang buat publik).
