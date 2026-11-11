import sqlite3

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Tabel Users (NUPTK 16 digit, Peg.ID 14 digit, atau NISN 10 digit)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL
                )''')

    # Tabel Siswa (Tanpa kolom kelas)
    c.execute('''CREATE TABLE IF NOT EXISTS siswa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nisn TEXT UNIQUE NOT NULL,
                    nama TEXT NOT NULL
                )''')

    # Tabel Master Tagihan (Tanpa SPP bulanan, berfokus pada tagihan global/cicilan)
    c.execute('''CREATE TABLE IF NOT EXISTS master_tagihan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama_tagihan TEXT NOT NULL,
                    kategori TEXT NOT NULL,
                    nominal REAL NOT NULL
                )''')

    # Tabel Transaksi Tagihan Siswa (Ditambahkan metode_bayar)
    c.execute('''CREATE TABLE IF NOT EXISTS transaksi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    siswa_id INTEGER,
                    master_tagihan_id INTEGER,
                    status TEXT DEFAULT 'Pending',
                    metode_bayar TEXT,
                    FOREIGN KEY(siswa_id) REFERENCES siswa(id),
                    FOREIGN KEY(master_tagihan_id) REFERENCES master_tagihan(id)
                )''')

    # Tabel Kas Masuk & Keluar
    c.execute('''CREATE TABLE IF NOT EXISTS kas_masuk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tanggal TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sumber TEXT NOT NULL,
                    keterangan TEXT,
                    nominal REAL NOT NULL
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS kas_keluar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tanggal TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    kategori TEXT NOT NULL,
                    keterangan TEXT,
                    nominal REAL NOT NULL
                )''')

    # Akun Default Internal
    users = [
        ('1234567890123456', 'password123', 'kepsek'), # NUPTK Kepsek/Bendahara (16 Digit)
        ('12345678901234', 'password123', 'tu')        # Peg.ID Staff TU (14 Digit)
    ]
    c.executemany("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", users)

    conn.commit()
    conn.close()
    print("Database berhasil diinisialisasi dengan struktur baru!")

if __name__ == '__main__':
    init_db()