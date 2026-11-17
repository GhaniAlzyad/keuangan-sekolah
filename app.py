import os
import io
import sqlite3
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, g, session, redirect, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_ypi_arroja_garut_2026'
DATABASE = 'database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def hitung_ringkasan_keuangan(db):
    # --- 1. PEMASUKAN HULU ---
    # Titipan Siswa Lunas per Jenjang (via Rekening Induk -> Kas Unit)
    titipan_mts = db.execute('''
        SELECT SUM(m.nominal) as total FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Lunas' AND s.jenjang = 'MTs'
    ''').fetchone()['total'] or 0

    titipan_ma = db.execute('''
        SELECT SUM(m.nominal) as total FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Lunas' AND s.jenjang = 'MA'
    ''').fetchone()['total'] or 0

    # Dana BOS & Subsidi Yayasan
    bos_mts = db.execute("SELECT SUM(nominal) as total FROM kas_masuk WHERE unit = 'MTs'").fetchone()['total'] or 0
    bos_ma = db.execute("SELECT SUM(nominal) as total FROM kas_masuk WHERE unit = 'MA'").fetchone()['total'] or 0
    kas_masuk_yayasan = db.execute("SELECT SUM(nominal) as total FROM kas_masuk WHERE unit = 'Yayasan'").fetchone()['total'] or 0

    # --- 2. EKSEKUSI PENGELUARAN ---
    # Pengeluaran Langsung MTs
    belanja_bos_mts = db.execute("SELECT SUM(nominal) as total FROM kas_keluar WHERE unit = 'MTs' AND jenis_belanja = 'Operasional BOS'").fetchone()['total'] or 0
    belanja_siswa_mts = db.execute("SELECT SUM(nominal) as total FROM kas_keluar WHERE unit = 'MTs' AND jenis_belanja = 'Kebutuhan Siswa'").fetchone()['total'] or 0

    # Pengeluaran Langsung MA
    belanja_bos_ma = db.execute("SELECT SUM(nominal) as total FROM kas_keluar WHERE unit = 'MA' AND jenis_belanja = 'Operasional BOS'").fetchone()['total'] or 0
    belanja_siswa_ma = db.execute("SELECT SUM(nominal) as total FROM kas_keluar WHERE unit = 'MA' AND jenis_belanja = 'Kebutuhan Siswa'").fetchone()['total'] or 0

    # Pengeluaran Shared Cost Yayasan & Distribusi Beban (Misal 60% MTs : 40% MA)
    list_shared = db.execute("SELECT nominal, persen_mts, persen_ma FROM kas_keluar WHERE unit = 'Yayasan'").fetchall()
    total_shared_yayasan = sum(r['nominal'] for r in list_shared)
    beban_bersama_mts = sum(round(r['nominal'] * (r['persen_mts'] / 100.0)) for r in list_shared)
    beban_bersama_ma = sum(round(r['nominal'] * (r['persen_ma'] / 100.0)) for r in list_shared)

    # --- 3. SISA SALDO PER KANTONG KAS ---
    total_masuk_mts = bos_mts + titipan_mts
    total_keluar_langsung_mts = belanja_bos_mts + belanja_siswa_mts
    saldo_kas_mts = total_masuk_mts - total_keluar_langsung_mts

    total_masuk_ma = bos_ma + titipan_ma
    total_keluar_langsung_ma = belanja_bos_ma + belanja_siswa_ma
    saldo_kas_ma = total_masuk_ma - total_keluar_langsung_ma

    saldo_kas_yayasan = kas_masuk_yayasan - total_shared_yayasan

    # --- 4. KONSOLIDASI YAYASAN ---
    total_pemasukan_konsolidasi = total_masuk_mts + total_masuk_ma + kas_masuk_yayasan
    total_pengeluaran_konsolidasi = total_keluar_langsung_mts + total_keluar_langsung_ma + total_shared_yayasan
    saldo_konsolidasi = saldo_kas_mts + saldo_kas_ma + saldo_kas_yayasan

    return {
        'bos_mts': bos_mts, 'titipan_mts': titipan_mts,
        'total_masuk_mts': total_masuk_mts,
        'belanja_bos_mts': belanja_bos_mts, 'belanja_siswa_mts': belanja_siswa_mts,
        'beban_bersama_mts': beban_bersama_mts,
        'total_keluar_langsung_mts': total_keluar_langsung_mts,
        'total_beban_unit_mts': total_keluar_langsung_mts + beban_bersama_mts,
        'saldo_kas_mts': saldo_kas_mts,

        'bos_ma': bos_ma, 'titipan_ma': titipan_ma,
        'total_masuk_ma': total_masuk_ma,
        'belanja_bos_ma': belanja_bos_ma, 'belanja_siswa_ma': belanja_siswa_ma,
        'beban_bersama_ma': beban_bersama_ma,
        'total_keluar_langsung_ma': total_keluar_langsung_ma,
        'total_beban_unit_ma': total_keluar_langsung_ma + beban_bersama_ma,
        'saldo_kas_ma': saldo_kas_ma,

        'kas_masuk_yayasan': kas_masuk_yayasan,
        'total_shared_yayasan': total_shared_yayasan,
        'saldo_kas_yayasan': saldo_kas_yayasan,

        'total_pemasukan_konsolidasi': total_pemasukan_konsolidasi,
        'total_pengeluaran_konsolidasi': total_pengeluaran_konsolidasi,
        'saldo_konsolidasi': saldo_konsolidasi
    }

# ==========================================
# 1. AUTHENTICATION & DASHBOARD
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if session.get('role'):
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['role'] = user['role']
            session['username'] = user['username']
            session['nama'] = user['nama']
            return redirect('/dashboard')
        else:
            return render_template('login.html', error="NUPTK/Peg.ID/NISN atau Password salah!")
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('role'):
        return redirect('/')
        
    role = session.get('role')
    username = session.get('username')
    db = get_db()

    keuangan = {}
    total_siswa_mts = total_siswa_ma = total_menunggu_validasi = 0
    wm_belum_lunas = wm_menunggu = wm_lunas = 0
    nama_siswa_wm = ""
    jenjang_wm = ""

    if role in ['kepsek', 'bendahara']:
        keuangan = hitung_ringkasan_keuangan(db)

    elif role == 'tu':
        total_siswa_mts = db.execute("SELECT COUNT(*) as total FROM siswa WHERE jenjang = 'MTs'").fetchone()['total'] or 0
        total_siswa_ma = db.execute("SELECT COUNT(*) as total FROM siswa WHERE jenjang = 'MA'").fetchone()['total'] or 0
        total_menunggu_validasi = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE status = 'Menunggu Validasi'").fetchone()['total'] or 0

    elif role == 'walimurid':
        siswa = db.execute("SELECT id, nama, jenjang, kelas FROM siswa WHERE nisn = ?", (username,)).fetchone()
        if siswa:
            nama_siswa_wm = siswa['nama']
            jenjang_wm = f"{siswa['jenjang']} ({siswa['kelas']})"
            s_id = siswa['id']
            wm_belum_lunas = db.execute('''
                SELECT SUM(m.nominal) as total FROM transaksi t 
                JOIN master_tagihan m ON t.master_tagihan_id = m.id 
                WHERE t.siswa_id = ? AND t.status = 'Pending'
            ''', (s_id,)).fetchone()['total'] or 0
            wm_menunggu = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE siswa_id = ? AND status = 'Menunggu Validasi'", (s_id,)).fetchone()['total'] or 0
            wm_lunas = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE siswa_id = ? AND status = 'Lunas'", (s_id,)).fetchone()['total'] or 0

    return render_template('dashboard.html', 
                           role=role, username=username, keuangan=keuangan,
                           total_siswa_mts=total_siswa_mts, total_siswa_ma=total_siswa_ma,
                           total_menunggu_validasi=total_menunggu_validasi,
                           wm_belum_lunas=wm_belum_lunas, wm_menunggu=wm_menunggu, wm_lunas=wm_lunas,
                           nama_siswa_wm=nama_siswa_wm, jenjang_wm=jenjang_wm)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==========================================
# 2. FITUR BENDAHARA & KEPSEK (Master Titipan & Arus Kas Unit)
# ==========================================
@app.route('/bendahara/tagihan', methods=['GET', 'POST'])
def master_tagihan():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    if request.method == 'POST':
        nama_tagihan = request.form.get('nama_tagihan')
        nominal = request.form.get('nominal')
        kategori = request.form.get('kategori')
        jenjang = request.form.get('jenjang')
        db.execute("INSERT INTO master_tagihan (nama_tagihan, nominal, kategori, jenjang, is_active) VALUES (?, ?, ?, ?, 1)", 
                   (nama_tagihan, nominal, kategori, jenjang))
        db.commit()
        return redirect('/bendahara/tagihan')
            
    data_tagihan = db.execute("SELECT * FROM master_tagihan WHERE is_active = 1 ORDER BY jenjang ASC, id DESC").fetchall()
    return render_template('bendahara_tagihan.html', tagihan=data_tagihan, role=session.get('role'), username=session.get('username'))

@app.route('/hapus/tagihan/<int:id>', methods=['POST'])
def hapus_tagihan(id):
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/bendahara/tagihan')
    db = get_db()
    db.execute("UPDATE master_tagihan SET is_active = 0 WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/tagihan')

@app.route('/bendahara/kas', methods=['GET', 'POST'])
def kelola_kas():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    if request.method == 'POST':
        jenis = request.form.get('jenis')
        unit = request.form.get('unit')
        nominal = int(request.form.get('nominal'))
        keterangan = request.form.get('keterangan')
        
        if jenis == 'masuk':
            sumber = request.form.get('sumber_masuk')
            db.execute("INSERT INTO kas_masuk (unit, sumber, nominal, keterangan) VALUES (?, ?, ?, ?)",
                       (unit, sumber, nominal, keterangan))
        elif jenis == 'keluar':
            jenis_belanja = request.form.get('jenis_belanja')
            kategori_keluar = request.form.get('kategori_keluar')
            persen_mts = int(request.form.get('persen_mts') or 0)
            persen_ma = int(request.form.get('persen_ma') or 0)
            
            if unit != 'Yayasan':
                persen_mts = 100 if unit == 'MTs' else 0
                persen_ma = 100 if unit == 'MA' else 0

            db.execute('''
                INSERT INTO kas_keluar (unit, jenis_belanja, kategori, nominal, persen_mts, persen_ma, keterangan)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (unit, jenis_belanja, kategori_keluar, nominal, persen_mts, persen_ma, keterangan))
        db.commit()
        return redirect('/bendahara/kas')
        
    keuangan = hitung_ringkasan_keuangan(db)
    pemasukan_hulu = db.execute("SELECT * FROM kas_masuk ORDER BY id DESC").fetchall()
    pengeluaran_unit = db.execute("SELECT * FROM kas_keluar ORDER BY id DESC").fetchall()
    return render_template('bendahara_kas.html', 
                           keuangan=keuangan, masuk=pemasukan_hulu, keluar=pengeluaran_unit,
                           role=session.get('role'), username=session.get('username'))

@app.route('/hapus/kas_masuk/<int:id>', methods=['POST'])
def hapus_kas_masuk(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/bendahara/kas')
    db = get_db()
    db.execute("DELETE FROM kas_masuk WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/kas')

@app.route('/hapus/kas_keluar/<int:id>', methods=['POST'])
def hapus_kas_keluar(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/bendahara/kas')
    db = get_db()
    db.execute("DELETE FROM kas_keluar WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/kas')

# ==========================================
# 3. FITUR TATA USAHA (TU)
# ==========================================
@app.route('/tu/siswa', methods=['GET', 'POST'])
def tu_siswa():
    if session.get('role') != 'tu':
        return redirect('/')
    
    db = get_db()
    if request.method == 'POST':
        nisn = request.form['nisn'].strip()
        nama = request.form['nama'].strip()
        jenjang = request.form.get('jenjang', 'MTs')
        kelas = request.form.get('kelas', '-').strip()
        hashed_pw = generate_password_hash(nisn)
        
        try:
            db.execute("INSERT INTO siswa (nisn, nama, jenjang, kelas) VALUES (?, ?, ?, ?)", (nisn, nama, jenjang, kelas))
            db.execute("INSERT INTO users (username, nama, password, role) VALUES (?, ?, ?, 'walimurid')", 
                       (nisn, nama, hashed_pw))
            db.commit()
        except sqlite3.IntegrityError:
            pass
        return redirect('/tu/siswa')
        
    siswa = db.execute("SELECT * FROM siswa ORDER BY jenjang ASC, nama ASC").fetchall()
    return render_template('tu_siswa.html', siswa=siswa, role=session.get('role'), username=session.get('username'))

@app.route('/edit/siswa/<int:id>', methods=['POST'])
def edit_siswa(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    siswa_lama = db.execute("SELECT nisn FROM siswa WHERE id = ?", (id,)).fetchone()
    nama_baru = request.form.get('nama').strip()
    nisn_baru = request.form.get('nisn').strip()
    jenjang_baru = request.form.get('jenjang', 'MTs')
    kelas_baru = request.form.get('kelas', '-').strip()
    
    if siswa_lama:
        db.execute("UPDATE siswa SET nama = ?, nisn = ?, jenjang = ?, kelas = ? WHERE id = ?",
                   (nama_baru, nisn_baru, jenjang_baru, kelas_baru, id))
        db.execute("UPDATE users SET username = ?, nama = ? WHERE username = ? AND role = 'walimurid'", 
                   (nisn_baru, nama_baru, siswa_lama['nisn']))
        db.commit()
    return redirect('/tu/siswa')

@app.route('/hapus/siswa/<int:id>', methods=['POST'])
def hapus_siswa(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    siswa = db.execute("SELECT nisn FROM siswa WHERE id = ?", (id,)).fetchone()
    if siswa:
        db.execute("DELETE FROM transaksi WHERE siswa_id = ?", (id,))
        db.execute("DELETE FROM users WHERE username = ? AND role = 'walimurid'", (siswa['nisn'],))
        db.execute("DELETE FROM siswa WHERE id = ?", (id,))
        db.commit()
    return redirect('/tu/siswa')

@app.route('/tu/assign_tagihan', methods=['GET', 'POST'])
def assign_tagihan():
    if session.get('role') != 'tu':
        return redirect('/')
    db = get_db()
    pesan_error = None
    
    if request.method == 'POST':
        siswa_id = request.form.get('siswa_id')
        tagihan_id = request.form.get('tagihan_id')
        
        cek_duplikat = db.execute("SELECT id FROM transaksi WHERE siswa_id = ? AND master_tagihan_id = ?", 
                                  (siswa_id, tagihan_id)).fetchone()
        if cek_duplikat:
            pesan_error = "Tagihan tersebut sudah pernah diberikan kepada siswa ini!"
        else:
            db.execute("INSERT INTO transaksi (siswa_id, master_tagihan_id, status) VALUES (?, ?, 'Pending')", 
                       (siswa_id, tagihan_id))
            db.commit()
            return redirect('/tu/assign_tagihan')
        
    daftar_siswa = db.execute("SELECT id, nama, nisn, jenjang, kelas FROM siswa ORDER BY jenjang ASC, nama ASC").fetchall()
    daftar_tagihan = db.execute("SELECT id, nama_tagihan, nominal, jenjang FROM master_tagihan WHERE is_active = 1 ORDER BY jenjang ASC").fetchall()
    riwayat_tagihan = db.execute('''
        SELECT t.id, s.nama, s.jenjang, m.nama_tagihan, m.nominal, t.status 
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        ORDER BY t.id DESC
    ''').fetchall()
    
    return render_template('tu_assign_tagihan.html', 
                           siswa=daftar_siswa, tagihan=daftar_tagihan, riwayat=riwayat_tagihan,
                           error=pesan_error, role=session.get('role'), username=session.get('username'))

@app.route('/hapus/transaksi/<int:id>', methods=['POST'])
def hapus_transaksi(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    db.execute("DELETE FROM transaksi WHERE id = ?", (id,))
    db.commit()
    return redirect('/tu/assign_tagihan')

@app.route('/tu/validasi', methods=['GET', 'POST'])
def tu_validasi():
    if session.get('role') != 'tu':
        return redirect('/')

    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        transaksi_id = request.form.get('transaksi_id')
        aksi = request.form.get('aksi')
        waktu_sekarang = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if aksi == 'Terima':
            cursor.execute("UPDATE transaksi SET status = 'Lunas', tanggal_validasi = ? WHERE id = ?", (waktu_sekarang, transaksi_id))
            db.commit()
        elif aksi == 'Tolak':
            cursor.execute("UPDATE transaksi SET status = 'Pending', metode_bayar = NULL, tanggal_bayar = NULL WHERE id = ?", (transaksi_id,))
            db.commit()

        return redirect('/tu/validasi')

    data_validasi = cursor.execute('''
        SELECT t.id, s.nama, s.nisn, s.jenjang, m.nama_tagihan, m.nominal, t.metode_bayar, t.tanggal_bayar
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Menunggu Validasi'
        ORDER BY t.id ASC
    ''').fetchall()

    riwayat_lunas = cursor.execute('''
        SELECT t.id, s.nama, s.nisn, s.jenjang, m.nama_tagihan, m.nominal, t.metode_bayar, t.tanggal_validasi
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Lunas'
        ORDER BY t.tanggal_validasi DESC, t.id DESC
        LIMIT 20
    ''').fetchall()
    
    return render_template('tu_validasi.html', 
                           validasi=data_validasi, riwayat_lunas=riwayat_lunas,
                           role=session.get('role'), username=session.get('username'))

# ==========================================
# 4. FITUR WALI MURID
# ==========================================
@app.route('/walimurid/tagihan/<nisn>', methods=['GET', 'POST'])
def walimurid_tagihan(nisn):
    if session.get('role') != 'walimurid' or session.get('username') != nisn:
        return redirect('/')

    db = get_db()
    
    if request.method == 'POST':
        transaksi_id = request.form.get('transaksi_id')
        metode_bayar = request.form.get('metode_bayar')
        waktu_bayar = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        db.execute('''
            UPDATE transaksi 
            SET status = 'Menunggu Validasi', metode_bayar = ?, tanggal_bayar = ? 
            WHERE id = ?
        ''', (metode_bayar, waktu_bayar, transaksi_id))
        db.commit()
        return redirect(f'/walimurid/tagihan/{nisn}')

    siswa = db.execute("SELECT id, nama, jenjang, kelas FROM siswa WHERE nisn = ?", (nisn,)).fetchone()
    if not siswa:
        return "<h3>Data siswa tidak ditemukan. Silakan lapor ke TU.</h3>"
        
    tagihan_siswa = db.execute('''
        SELECT t.id, m.nama_tagihan, m.nominal, t.status, t.metode_bayar, t.tanggal_bayar
        FROM transaksi t
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.siswa_id = ?
        ORDER BY t.id DESC
    ''', (siswa['id'],)).fetchall()
    
    return render_template('walimurid_tagihan.html', 
                           nama_siswa=siswa['nama'], jenjang_siswa=siswa['jenjang'], kelas_siswa=siswa['kelas'],
                           tagihan=tagihan_siswa, role=session.get('role'), username=session.get('username'))

# ==========================================
# 5. LAPORAN JENJANG (MTs & MA), KONSOLIDASI YAYASAN & CETAK PDF
# ==========================================
@app.route('/laporan')
def laporan():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    keuangan = hitung_ringkasan_keuangan(db)
    keluar_mts = db.execute("SELECT * FROM kas_keluar WHERE unit = 'MTs' ORDER BY id DESC").fetchall()
    keluar_ma = db.execute("SELECT * FROM kas_keluar WHERE unit = 'MA' ORDER BY id DESC").fetchall()
    keluar_yayasan = db.execute("SELECT * FROM kas_keluar WHERE unit = 'Yayasan' ORDER BY id DESC").fetchall()
    rincian_masuk = db.execute("SELECT * FROM kas_masuk ORDER BY id DESC").fetchall()
    
    return render_template('laporan.html', 
                           keuangan=keuangan,
                           keluar_mts=keluar_mts, keluar_ma=keluar_ma, keluar_yayasan=keluar_yayasan,
                           rincian_masuk=rincian_masuk,
                           role=session.get('role'), username=session.get('username'))

@app.route('/laporan/pdf')
def cetak_pdf():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    k = hitung_ringkasan_keuangan(db)

    pdf = FPDF()
    pdf.add_page()
    
    # Kop Surat YPI ARROJA
    pdf.set_font("helvetica", "B", 13)
    pdf.cell(0, 6, "YAYASAN PENDIDIKAN ISLAM ARROJA", ln=True, align="C")
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 5, "MADRASAH TSANAWIYAH & ALIYAH ARROJA", ln=True, align="C")
    pdf.set_font("helvetica", "", 8)
    pdf.cell(0, 4, "Jl. Garut - Tasik KM. 11 Kp. Cigarungsang, Ds. Mekarsari, Kec. Cilawu, Kab. Garut - 44181", ln=True, align="C")
    pdf.cell(0, 4, "Telp: 082315467766 | Email: mtsarroja@gmail.com & masarroja@gmail.com", ln=True, align="C")
    pdf.ln(3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 7, "LAPORAN KEUANGAN PER JENJANG & KONSOLIDASI YAYASAN", ln=True, align="C")
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"Dicetak pada: {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True, align="C")
    pdf.ln(6)

    def rp(val):
        return f"Rp {val:,.0f}".replace(',', '.')

    # Blok 1: Laporan MTs
    pdf.set_fill_color(230, 242, 255)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 8, " 1. LAPORAN KEUANGAN JENJANG MTs ARROJA", border=1, fill=True, ln=True)
    pdf.set_font("helvetica", "", 9)
    rows_mts = [
        ("Realisasi Dana BOS MTs", rp(k['bos_mts'])),
        ("Realisasi Titipan Siswa MTs (Lunas)", rp(k['titipan_mts'])),
        ("Belanja Operasional BOS MTs", f"- {rp(k['belanja_bos_mts'])}"),
        ("Belanja Kebutuhan Siswa MTs", f"- {rp(k['belanja_siswa_mts'])}"),
        ("Alokasi Beban Bersama Yayasan (Porsi MTs)", rp(k['beban_bersama_mts'])),
        ("SISA SALDO KAS UNIT MTs", rp(k['saldo_kas_mts'])),
    ]
    for label, val in rows_mts:
        is_bold = "SISA SALDO" in label
        pdf.set_font("helvetica", "B" if is_bold else "", 9)
        pdf.cell(125, 7, f"   {label}", border=1)
        pdf.cell(65, 7, f"{val} ", border=1, align="R", ln=True)
    pdf.ln(5)

    # Blok 2: Laporan MA
    pdf.set_fill_color(230, 255, 240)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 8, " 2. LAPORAN KEUANGAN JENJANG MA ARROJA", border=1, fill=True, ln=True)
    rows_ma = [
        ("Realisasi Dana BOS MA", rp(k['bos_ma'])),
        ("Realisasi Titipan Siswa MA (Lunas)", rp(k['titipan_ma'])),
        ("Belanja Operasional BOS MA", f"- {rp(k['belanja_bos_ma'])}"),
        ("Belanja Kebutuhan Siswa MA", f"- {rp(k['belanja_siswa_ma'])}"),
        ("Alokasi Beban Bersama Yayasan (Porsi MA)", rp(k['beban_bersama_ma'])),
        ("SISA SALDO KAS UNIT MA", rp(k['saldo_kas_ma'])),
    ]
    for label, val in rows_ma:
        is_bold = "SISA SALDO" in label
        pdf.set_font("helvetica", "B" if is_bold else "", 9)
        pdf.cell(125, 7, f"   {label}", border=1)
        pdf.cell(65, 7, f"{val} ", border=1, align="R", ln=True)
    pdf.ln(5)

    # Blok 3: Konsolidasi Yayasan
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 8, " 3. LAPORAN KONSOLIDASI YAYASAN (MTs + MA + KAS INDUK)", border=1, fill=True, ln=True)
    rows_konsol = [
        ("Pemasukan Kas Induk / Subsidi Yayasan", rp(k['kas_masuk_yayasan'])),
        ("Pengeluaran Beban Bersama Yayasan (Listrik, Air, Satpam, dll)", f"- {rp(k['total_shared_yayasan'])}"),
        ("Sisa Saldo Kas Yayasan (Shared Cost)", rp(k['saldo_kas_yayasan'])),
        ("TOTAL PEMASUKAN KONSOLIDASI YAYASAN", rp(k['total_pemasukan_konsolidasi'])),
        ("TOTAL PENGELUARAN KONSOLIDASI YAYASAN", f"- {rp(k['total_pengeluaran_konsolidasi'])}"),
        ("TOTAL SALDO AKHIR KONSOLIDASI YAYASAN", rp(k['saldo_konsolidasi'])),
    ]
    for label, val in rows_konsol:
        is_bold = "TOTAL" in label
        pdf.set_font("helvetica", "B" if is_bold else "", 9)
        pdf.cell(125, 7, f"   {label}", border=1)
        pdf.cell(65, 7, f"{val} ", border=1, align="R", ln=True)

    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    
    return send_file(pdf_buffer, as_attachment=True, download_name="Laporan_Konsolidasi_YPI_ARROJA.pdf", mimetype="application/pdf")

@app.route('/invoice/pdf/<int:transaksi_id>')
def cetak_invoice_pdf(transaksi_id):
    role = session.get('role')
    username = session.get('username')
    if not role:
        return redirect('/')

    db = get_db()
    trx = db.execute('''
        SELECT t.id, t.status, t.metode_bayar, t.tanggal_validasi,
               s.nama AS nama_siswa, s.nisn, s.jenjang, s.kelas,
               m.nama_tagihan, m.kategori, m.nominal
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.id = ?
    ''', (transaksi_id,)).fetchone()

    if not trx or trx['status'] != 'Lunas':
        return "<h3>Invoice tidak ditemukan atau transaksi belum lunas.</h3>"

    if role == 'walimurid' and trx['nisn'] != username:
        return redirect('/')

    pdf = FPDF(orientation='P', unit='mm', format='A5')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)

    # Kop Surat Resmi YPI ARROJA
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 5, "YAYASAN PENDIDIKAN ISLAM ARROJA", ln=True, align="C")
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 5, "MADRASAH TSANAWIYAH & ALIYAH ARROJA", ln=True, align="C")
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, "Jl. Garut - Tasik KM. 11 Kp. Cigarungsang, Ds. Mekarsari, Kec. Cilawu", ln=True, align="C")
    pdf.cell(0, 3.5, "Kab. Garut, Prov. Jawa Barat - 44181 | Telp: 082315467766", ln=True, align="C")
    pdf.cell(0, 3.5, "Email: mtsarroja@gmail.com & masarroja@gmail.com", ln=True, align="C")
    
    pdf.ln(2)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 138, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.line(10, pdf.get_y() + 1, 138, pdf.get_y() + 1)
    pdf.ln(5)

    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 6, "BUKTI PEMBAYARAN TITIPAN SISWA (INVOICE)", ln=True, align="C")
    pdf.set_font("helvetica", "", 9)
    no_inv = f"INV/{trx['jenjang']}/{datetime.now().strftime('%Y%m')}/TRX-{trx['id']:04d}"
    pdf.cell(0, 5, f"Nomor Dokumen: {no_inv}", ln=True, align="C")
    pdf.ln(4)

    tgl_val = str(trx['tanggal_validasi']) if trx['tanggal_validasi'] else datetime.now().strftime('%Y-%m-%d %H:%M')
    info_baris = [
        ("Nama Siswa", f": {trx['nama_siswa']}"),
        ("NISN / Unit", f": {trx['nisn']} ({trx['jenjang']} ARROJA - Kelas {trx['kelas']})"),
        ("Rek. Penerima", f": Rekening Induk YPI ARROJA ({trx['metode_bayar'] or '-'})"),
        ("Waktu Validasi", f": {tgl_val}"),
    ]
    for label, val in info_baris:
        pdf.cell(35, 6, label, border=0)
        pdf.set_font("helvetica", "B" if label == "Nama Siswa" else "", 9)
        pdf.cell(0, 6, val, border=0, ln=True)
        pdf.set_font("helvetica", "", 9)

    pdf.ln(4)

    pdf.set_fill_color(230, 240, 255)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(68, 8, " Keterangan Titipan / Tagihan", border=1, fill=True)
    pdf.cell(25, 8, " Kategori", border=1, fill=True, align="C")
    pdf.cell(35, 8, "Nominal ", border=1, fill=True, align="R", ln=True)

    pdf.set_font("helvetica", "", 9)
    nominal_str = f"Rp {trx['nominal']:,.0f}".replace(',', '.')
    pdf.cell(68, 9, f" {trx['nama_tagihan']}", border=1)
    pdf.cell(25, 9, f" {trx['kategori']}", border=1, align="C")
    pdf.cell(35, 9, f"{nominal_str} ", border=1, align="R", ln=True)

    pdf.set_font("helvetica", "B", 9)
    pdf.cell(93, 8, " TOTAL DIBAYAR", border=1, fill=True)
    pdf.cell(35, 8, f"{nominal_str} ", border=1, fill=True, align="R", ln=True)

    pdf.ln(6)

    pdf.set_text_color(25, 135, 84)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(60, 10, "[ STATUS: LUNAS / SAH ]", border=1, align="C")
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 8)
    pdf.cell(68, 5, "Tata Usaha YPI ARROJA,", ln=True, align="R")
    pdf.ln(10)
    petugas = session.get('nama') if role in ['tu', 'bendahara', 'kepsek'] else "Staff Tata Usaha"
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 5, f"( {petugas} )", ln=True, align="R")

    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    nama_file = f"Invoice_{trx['jenjang']}_{trx['nisn']}_{trx['nama_tagihan'].replace(' ', '_')}.pdf"
    return send_file(pdf_buffer, as_attachment=True, download_name=nama_file, mimetype="application/pdf")

if __name__ == '__main__':
    app.run(debug=True)