import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

cursor.executescript('''
    DROP TABLE IF EXISTS users;
    DROP TABLE IF EXISTS siswa;
    DROP TABLE IF EXISTS master_tagihan;
    DROP TABLE IF EXISTS transaksi;
    DROP TABLE IF EXISTS kas_masuk;
    DROP TABLE IF EXISTS kas_keluar;
''')

# 1. Tabel Users
cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        nama TEXT NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
''')

# 2. Tabel Siswa (Dilengkapi Jenjang MTs / MA & Kelas)
cursor.execute('''
    CREATE TABLE siswa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nisn TEXT UNIQUE NOT NULL,
        nama TEXT NOT NULL,
        jenjang TEXT NOT NULL DEFAULT 'MTs',
        kelas TEXT DEFAULT '-'
    )
''')

# 3. Tabel Master Tagihan (Titipan Siswa per Jenjang)
cursor.execute('''
    CREATE TABLE master_tagihan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_tagihan TEXT NOT NULL,
        nominal INTEGER NOT NULL,
        kategori TEXT NOT NULL,
        jenjang TEXT NOT NULL DEFAULT 'MTs',
        is_active INTEGER DEFAULT 1
    )
''')

# 4. Tabel Transaksi (Titipan Siswa MTs & MA via Rekening Induk Yayasan)
cursor.execute('''
    CREATE TABLE transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        siswa_id INTEGER NOT NULL,
        master_tagihan_id INTEGER NOT NULL,
        status TEXT DEFAULT 'Pending',
        metode_bayar TEXT,
        tanggal_bayar DATETIME,
        tanggal_validasi DATETIME,
        FOREIGN KEY (siswa_id) REFERENCES siswa (id),
        FOREIGN KEY (master_tagihan_id) REFERENCES master_tagihan (id)
    )
''')

# 5. Tabel Kas Masuk (Dana BOS MTs, Dana BOS MA, Donasi/Subsidi Yayasan)
cursor.execute('''
    CREATE TABLE kas_masuk (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit TEXT NOT NULL,
        sumber TEXT NOT NULL,
        nominal INTEGER NOT NULL,
        keterangan TEXT,
        tanggal DATETIME DEFAULT (datetime('now', 'localtime'))
    )
''')

# 6. Tabel Kas Keluar (Operasional BOS, Kebutuhan Siswa, & Beban Bersama 60:40)
cursor.execute('''
    CREATE TABLE kas_keluar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit TEXT NOT NULL,
        jenis_belanja TEXT NOT NULL,
        kategori TEXT NOT NULL,
        nominal INTEGER NOT NULL,
        persen_mts INTEGER DEFAULT 0,
        persen_ma INTEGER DEFAULT 0,
        keterangan TEXT,
        tanggal DATETIME DEFAULT (datetime('now', 'localtime'))
    )
''')

# Seed Akun Internal Default (Password: password123)
default_pw = generate_password_hash('password123')
akun_internal = [
    ('198001012005011001', 'Ibu Dwi Sofia Muharyani, M.Pd', default_pw, 'kepsek'),
    ('198505122010012002', '-', default_pw, 'bendahara'),
    ('199208172019031003', 'Sdr. Rika Nuraini, S.A.P', default_pw, 'tu')
]
cursor.executemany("INSERT INTO users (username, nama, password, role) VALUES (?, ?, ?, ?)", akun_internal)

conn.commit()
conn.close()
print("Database Keuangan ARROJA (Skema Arus Kas MTs, MA & Yayasan) berhasil dibuat!")