# Nocturne Manager

Bot Discord dengan 2 fitur utama:

1. **Notifikasi Join/Leave** — punya panel builder interaktif (tombol + live preview) buat custom embed tanpa perlu edit kode.
2. **Notifikasi Status Bot** — kirim embed Online / Maintenance / Update / Offline dengan indikator custom emoji.

Dibangun pakai `discord.py` 2.x, slash command penuh, siap deploy ke **Railway**.

---

## 1. Setup Bot di Discord Developer Portal

1. Buka https://discord.com/developers/applications → **New Application** → beri nama `Nocturne Manager`.
2. Tab **Bot** → klik **Reset Token**, simpan token itu (jangan disebar).
3. Di tab **Bot**, aktifkan **SERVER MEMBERS INTENT** (wajib, dipakai buat deteksi join/leave).
4. Tab **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Manage Webhooks` (opsional), `View Channels`
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
```

Jalankan:

```bash
python main.py
```

---

## 3. Deploy ke Railway

1. Push project ini ke GitHub repo baru.
2. Di Railway: **New Project → Deploy from GitHub repo** → pilih repo ini.
3. Railway otomatis detect `Procfile` (`worker: python main.py`) — pastikan service dijalankan sebagai **worker**, bukan web (karena bot Discord tidak butuh port HTTP).
4. Masuk ke tab **Variables**, tambahkan:
   - `DISCORD_TOKEN` = token bot kamu
   - `GUILD_ID` = (opsional, hapus/skip kalau mau slash command global di semua server)
5. Deploy. Cek log — kalau muncul `Login sebagai Nocturne Manager (ID: ...)` berarti sukses.

> ⚠️ Data `data/*.json` disimpan di filesystem container. Railway punya ephemeral filesystem by default — kalau redeploy, data ikut ke-reset. Kalau mau data join/leave & status persisten, tambahkan **Railway Volume** dan mount ke folder `data/`.

---

## 4. Cara Pakai Slash Command

### Join/Leave

| Command | Fungsi |
|---|---|
| `/joinleave builder type:Join` | Buka panel builder untuk embed **Join** (live preview, hanya kamu yang lihat) |
| `/joinleave builder type:Leave` | Buka panel builder untuk embed **Leave** |
| `/joinleave toggle type:Join enabled:True/False` | Aktif/nonaktifkan cepat tanpa buka builder |
| `/joinleave test type:Join` | Kirim contoh embed ke channel yang sudah diset (pakai data kamu sendiri) |

**Tombol di dalam Panel Builder:**

- 📝 **Title** — set judul embed
- 📄 **Description** — set deskripsi (bisa pakai variabel)
- 🖼️ **Thumbnail** — gambar kecil pojok kanan atas (bisa `{user_avatar}`)
- 🏳️ **Banner** — gambar besar di bawah embed
- 🎨 **Color** — warna embed (hex, contoh `#FFD54A`)
- ➕ **Field** — tambah field biasa (nama, isi, inline)
- 🔸 **Icon Field** — field dengan emoji di depan namanya
- ➖ **Separator** — tambah garis pembatas
- 🔗 **Row Link** — tambah tombol link di bawah embed (maks 5)
- 🧩 **Variable** — lihat daftar variabel yang bisa dipakai
- 🗑️ dropdown **Hapus field/separator** — hapus salah satu blok yang sudah dibuat
- 📌 dropdown **Set channel** — pilih channel tujuan notifikasi
- 🔌 **Enable/Disable** — aktif/nonaktifkan notifikasi ini
- ♻️ **Reset** — kembalikan ke default
- ✅ **Done** — kunci panel (perubahan sudah otomatis tersimpan dari awal)

**Variabel yang tersedia** (dipakai di Title/Description/Field/Thumbnail/Banner):

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

### Status Bot (mendukung banyak bot sekaligus)

Fitur ini dibuat buat kamu yang punya beberapa bot (JoyCannot, JOY UNIVERSE, dll) dan mau nampilin status masing-masing di satu channel yang sama. Tiap bot didaftarkan sekali, abis itu tinggal dipilih via autocomplete tiap kali mau update status.

| Command | Fungsi |
|---|---|
| `/status setup channel:#log-bot` | Set channel tujuan (dipakai bareng untuk semua bot) |
| `/status addbot name:"JoyCannot" icon:<url>` | Daftarkan bot baru yang mau dipantau |
| `/status editbot bot:<pilih> name:.. icon:..` | Edit nama/icon bot yang sudah terdaftar |
| `/status removebot bot:<pilih>` | Hapus bot dari daftar |
| `/status listbots` | Lihat semua bot yang terdaftar |
| `/status set bot:<pilih> status:Online message:"Semua fitur aktif"` | Kirim embed status bot tsb ke channel |
| `/status preview bot:<pilih> status:Maintenance` | Preview tanpa kirim (ephemeral) |

Parameter `bot:` pakai **autocomplete** — tinggal ketik beberapa huruf nama bot, Discord otomatis suggest dari daftar yang sudah kamu `addbot`.

**Contoh alur pakai:**
```
/status setup channel:#status-bot
/status addbot name:"JoyCannot" icon:https://link-avatar-joycannot.png
/status addbot name:"JOY UNIVERSE" icon:https://link-avatar-joyuniverse.png
/status set bot:JoyCannot status:Online
/status set bot:"JOY UNIVERSE" status:Maintenance message:"Lagi update ke stage 9"
```

Emoji indikator status diambil dari **`config/emojis.json`**. Edit file ini untuk pakai emoji custom server kamu:

```json
{
  "status_online": "<:online:1234567890123456789>",
  "status_maintenance": "<:maintenance:1234567890123456789>",
  "status_update": "<:update:1234567890123456789>",
  "status_offline": "<:offline:1234567890123456789>",
  "separator": "▬"
}
```

Cara ambil ID emoji custom: ketik `\:nama_emoji:` di channel Discord manapun (dengan backslash di depan), Discord akan menampilkan format lengkapnya `<:nama_emoji:id>` — copy itu ke file `emojis.json`.

---

## 5. Struktur Project

```
nocturne-manager/
├── main.py                  # entrypoint bot
├── requirements.txt
├── Procfile                  # start command untuk Railway
├── .env.example
├── config/
│   └── emojis.json            # emoji custom untuk status bot
├── cogs/
│   ├── joinleave.py           # listener on_member_join/remove + slash command
│   ├── panel_builder.py       # View interaktif + semua Modal builder
│   └── status_panel.py        # slash command status bot
├── utils/
│   ├── storage.py             # JSON storage atomic (aman dari corrupt saat restart)
│   ├── variables.py           # resolver variabel {user}, {server}, dll
│   └── embed_builder.py       # builder embed join/leave dari config
└── data/                      # auto-generated: joinleave.json, status.json
```

---

## 6. Permission yang Dibutuhkan

Semua command setting (`builder`, `setup`, `toggle`, `set`) butuh izin **Manage Server** dari user yang menjalankan — supaya cuma admin/staff yang bisa ubah setting-nya.
