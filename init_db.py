import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Reset bersih tabel
cursor.executescript('''
    DROP TABLE IF EXISTS users;
    DROP TABLE IF EXISTS siswa;
    DROP TABLE IF EXISTS master_tagihan;
    DROP TABLE IF EXISTS transaksi;
    DROP TABLE IF EXISTS kas_masuk;
    DROP TABLE IF EXISTS kas_keluar;
''')

# 1. Tabel Users (username = NUPTK/Peg.ID untuk internal, NISN untuk walimurid)
cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        nama TEXT NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
''')

# 2. Tabel Siswa
cursor.execute('''
    CREATE TABLE siswa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nisn TEXT UNIQUE NOT NULL,
        nama TEXT NOT NULL
    )
''')

# 3. Tabel Master Tagihan (Soft Delete is_active)
cursor.execute('''
    CREATE TABLE master_tagihan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_tagihan TEXT NOT NULL,
        nominal INTEGER NOT NULL,
        kategori TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    )
''')

# 4. Tabel Transaksi
cursor.execute('''
    CREATE TABLE transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        siswa_id INTEGER NOT NULL,
        master_tagihan_id INTEGER NOT NULL,
        status TEXT DEFAULT 'Pending',
        metode_bayar TEXT,
        bukti_bayar TEXT,
        tanggal_bayar DATETIME,
        tanggal_validasi DATETIME,
        FOREIGN KEY (siswa_id) REFERENCES siswa (id),
        FOREIGN KEY (master_tagihan_id) REFERENCES master_tagihan (id)
    )
''')

# 5. Tabel Kas Masuk & Keluar
cursor.execute('''
    CREATE TABLE kas_masuk (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sumber TEXT NOT NULL,
        nominal INTEGER NOT NULL,
        keterangan TEXT,
        tanggal DATETIME DEFAULT (datetime('now', 'localtime'))
    )
''')

cursor.execute('''
    CREATE TABLE kas_keluar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kategori TEXT NOT NULL,
        nominal INTEGER NOT NULL,
        keterangan TEXT,
        tanggal DATETIME DEFAULT (datetime('now', 'localtime'))
    )
''')

# Seed Akun Internal Default (Login menggunakan NUPTK/Peg.ID, password: password123)
default_pw = generate_password_hash('password123')
akun_internal = [
    ('123456789012345678', 'Dwi Sofia Muharyani, M.Pd', default_pw, 'kepsek'),
    ('123456789123456789', '-', default_pw, 'bendahara'),
    ('012345678901234567', 'Rika Nuraini, S.A.P', default_pw, 'tu')
]
cursor.executemany("INSERT INTO users (username, nama, password, role) VALUES (?, ?, ?, ?)", akun_internal)

conn.commit()
conn.close()
print("Database berhasil diperbarui! Akun internal menggunakan NUPTK/Peg.ID dengan password: password123")