# Sistem Manajemen Keuangan Sekolah 🏫💰

Sistem berbasis web untuk mengelola administrasi keuangan sekolah. Aplikasi ini dirancang untuk memudahkan pencatatan tagihan, validasi pembayaran, manajemen kas, dan pelaporan keuangan dengan integrasi pengiriman *invoice* otomatis melalui WhatsApp.

## 🌟 Fitur Utama

*   **Multi-Role Authentication**: Akses terpisah untuk Kepala Sekolah, Bendahara, Tata Usaha (TU), dan Wali Murid.
*   **Manajemen Siswa & Tagihan (CRUD)**: Pendataan siswa terintegrasi dengan pembuatan akun Wali Murid secara otomatis berdasarkan NISN.
*   **Validasi Pembayaran Interaktif**: Tata Usaha dapat menerima atau menolak bukti pembayaran dari Wali Murid.
*   **Integrasi Invoice WhatsApp**: Pengiriman nota lunas otomatis ke WhatsApp Wali Murid setelah pembayaran divalidasi.
*   **Pencatatan Kas (Masuk/Keluar)**: Pencatatan kas operasional sekolah selain dari tagihan siswa.
*   **Export Laporan PDF**: Pembuatan laporan *cash flow* dan riwayat pemasukan secara instan dalam format PDF.

## 🛠️ Teknologi yang Digunakan

*   **Backend**: Python, Flask
*   **Database**: SQLite
*   **Frontend**: HTML5, Bootstrap 5
*   **Library Tambahan**: `FPDF` (Export PDF), `urllib.parse` (WhatsApp Web URL Encoding)

## 🚀 Cara Instalasi dan Penggunaan

1. **Clone Repositori**
   ```bash
   git clone [https://github.com/username-anda/nama-repo-anda.git](https://github.com/username-anda/nama-repo-anda.git)
   cd nama-repo-anda

2. **Buat Virtual Environment** (Opsional namun disarankan)

   ```Bash
   python -m venv venv
   source venv/bin/activate  # Untuk Linux/Mac
   venv\Scripts\activate     # Untuk Windows

3. **Install Dependencies**
   Pastikan Anda menginstal Flask dan FPDF.

   ```Bash
   pip install flask fpdf

4. **Inisialisasi Database**
   Jalankan skrip inisialisasi untuk membuat file database.db beserta struktur tabelnya.

   ```Bash
   python init_db.py

5. **Jalankan Aplikasi**

   ```Bash
   python app.py
   
   Aplikasi akan berjalan di http://127.0.0.1:5000/


👥 Hak Akses (Role)
Sistem ini memiliki 4 peran pengguna dengan hak akses yang berbeda:

1. Kepala Sekolah: Melihat laporan keuangan dan rekapitulasi secara keseluruhan.

2. Bendahara: Mengelola master tagihan, mencatat kas masuk/keluar operasional, dan mencetak laporan PDF.

3. Tata Usaha (TU): Mengelola data siswa, menetapkan tagihan ke siswa, dan memvalidasi pembayaran dari Wali Murid.

4. Wali Murid: Melihat riwayat tagihan pribadi dan mengonfirmasi metode pembayaran. (Username dan Password menggunakan NISN Siswa).

🔒 Catatan Keamanan
Repositori ini dikonfigurasi untuk mengabaikan file database.db guna melindungi data pengguna. Jika ingin menguji coba, silakan jalankan python init_db.py di lokal mesin Anda untuk membuat database dummy baru.