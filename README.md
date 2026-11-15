# Keuangan ARROJA — Sistem Informasi Keuangan Sekolah
**Yayasan Pendidikan Islam Arroja (MTs & MA Arroja Garut)**

Aplikasi manajemen keuangan dan pembayaran siswa berbasis web yang dirancang khusus untuk operasional instansi pendidikan di **YPI ARROJA**. Sistem ini mencakup pengelolaan master tagihan, pencatatan arus kas (BOS/Hibah/Operasional), distribusi tagihan siswa, konfirmasi pembayaran wali murid via Transfer/QRIS & WhatsApp, hingga penerbitan kuitansi/invoice PDF berkop surat resmi sekolah.

---

## Fitur Utama

1. **Multi-Role Access Control (RBAC)**
   - **Kepala Sekolah & Bendahara** *(mendukung rangkap jabatan)*: Mengelola katalog master tagihan, mencatat arus kas masuk/keluar non-siswa, memantau saldo kas real-time, serta mencetak laporan arus kas PDF.
   - **Staff Tata Usaha (TU)**: Mengelola data siswa (otomatis membuat akun login wali murid), mendistribusikan tagihan ke siswa, memvalidasi pembayaran, serta menerbitkan dan mengirim Invoice PDF resmi via WhatsApp.
   - **Wali Murid**: Memantau rincian tagihan anak, memilih metode pembayaran (Transfer Bank / QRIS) untuk memunculkan tujuan pembayaran resmi sekolah, mengirim konfirmasi bukti bayar langsung ke WhatsApp TU, serta mengunduh bukti lunas resmi (PDF).

2. **Keamanan & Integritas Data**
   - Enkripsi password menggunakan `werkzeug.security` (PBKDF2-SHA256).
   - Perlindungan anti-IDOR pada rute wali murid (terkunci berdasarkan sesi NISN).
   - *Soft Delete* pada master tagihan agar riwayat transaksi lama tetap utuh.
   - Pencegahan duplikasi penugasan tagihan pada siswa yang sama.

3. **Dokumen Resmi Otomatis**
   - Pembuatan kuitansi/invoice PDF format A5 berkop surat resmi **Yayasan Pendidikan Islam Arroja** secara otomatis menggunakan pustaka `FPDF`.

---

## Struktur Proyek

```text
keuangan-arroja/
├── app.py                  # Aplikasi utama & rute pengendali Flask
├── init_db.py              # Skrip inisialisasi skema database & akun default
├── requirements.txt        # Daftar pustaka Python (Flask, Werkzeug, fpdf2)
├── static/
│   └── qris_sekolah.png    # Gambar kode QRIS resmi YPI ARROJA
└── templates/
    ├── base.html           # Template induk (Navbar & Tab Navigasi Persisten)
    ├── login.html          # Halaman autentikasi (NUPTK / Peg.ID / NISN)
    ├── dashboard.html      # Ringkasan kartu statistik dinamis sesuai role
    ├── bendahara_tagihan.html
    ├── bendahara_kas.html
    ├── tu_siswa.html
    ├── tu_assign_tagihan.html
    ├── tu_validasi.html
    ├── walimurid_tagihan.html
    └── laporan.html
```
## 🚀 Cara Instalasi dan Penggunaan

1. **Clone Repositori**
   ```bash
   git clone [https://github.com/username-anda/nama-repo-anda.git](https://github.com/username-anda/nama-repo-anda.git)
   cd nama-repo-anda
   ```
2. **Buat Virtual Environment** (Opsional namun disarankan)

   ```Bash
   python -m venv venv
   source venv/bin/activate  # Untuk Linux/Mac
   venv\Scripts\activate     # Untuk Windows
   ```
3. **Install Dependencies**
   Pastikan Anda menginstal Flask dan FPDF.

   ```Bash
   pip install flask fpdf
   ```

4. **Inisialisasi Database**
   Jalankan skrip inisialisasi untuk membuat file database.db beserta struktur tabelnya.
   ```Bash
   python init_db.py
   ```
5. **Jalankan Aplikasi**

   ```Bash
   python app.py
   ```  
Aplikasi akan berjalan di http://127.0.0.1:5000/


👥 Hak Akses (Role)
Sistem ini memiliki 4 peran pengguna dengan hak akses yang berbeda:

1. Kepala Sekolah: Melihat laporan keuangan dan rekapitulasi secara keseluruhan.

2. Bendahara: Mengelola master tagihan, mencatat kas masuk/keluar operasional, dan mencetak laporan PDF.

3. Tata Usaha (TU): Mengelola data siswa, menetapkan tagihan ke siswa, dan memvalidasi pembayaran dari Wali Murid.

4. Wali Murid: Melihat riwayat tagihan pribadi dan mengonfirmasi metode pembayaran. (Username dan Password menggunakan NISN Siswa).

Catatan untuk Akun Wali Murid: Akun wali murid dibuat secara otomatis saat Staff TU menambahkan data siswa baru. Username dan Password awal menggunakan 10 digit NISN siswa tersebut.

---

### Langkah Terakhir Sebelum Deploy:
1. Simpan kode di atas ke dalam `README.md`.
2. Pastikan file `requirements.txt` sudah dibuat dan gambar `qris_sekolah.png` sudah berada di dalam folder `static/`.
3. Jalankan `git add .`, `git commit -m "Update dokumentasi dan kesiapan deploy Keuangan ARROJA"`, lalu `git push`.
4. Lanjutkan tarik kode tersebut di **Bash Console PythonAnywhere** dan ikuti langkah konfigurasi WSGI yang sudah dibahas sebelumnya.