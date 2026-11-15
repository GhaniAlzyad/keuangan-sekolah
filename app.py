import os
import io
import sqlite3
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, g, session, redirect, flash
from flask import send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_ma_keuangan_production'
DATABASE = 'database.db'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

# ==========================================
# 1. AUTHENTICATION & DASHBOARD
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if session.get('role'):
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['role'] = user['role']
            session['username'] = user['username']
            session['nama'] = user['nama']  # Menyimpan nama asli ke dalam session
            return redirect('/dashboard')
        else:
            return render_template('login.html', error="NUPTK/NISN atau Password salah!")
            
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('role'):
        return redirect('/')
        
    role = session.get('role')
    username = session.get('username')
    
    total_tagihan = saldo_kas = total_transaksi = 0
    total_siswa = total_tagihan_assign = total_menunggu_validasi = 0
    wm_belum_lunas = wm_menunggu = wm_lunas = 0
    nama_siswa_wm = ""

    db = get_db()

    if role in ['kepsek', 'bendahara']:
        total_tagihan = db.execute("SELECT COUNT(*) as total FROM master_tagihan WHERE is_active = 1").fetchone()['total'] or 0
        
        masuk_siswa = db.execute("SELECT SUM(m.nominal) as total FROM transaksi t JOIN master_tagihan m ON t.master_tagihan_id = m.id WHERE t.status = 'Lunas'").fetchone()['total'] or 0
        masuk_lain = db.execute("SELECT SUM(nominal) as total FROM kas_masuk").fetchone()['total'] or 0
        pengeluaran = db.execute("SELECT SUM(nominal) as total FROM kas_keluar").fetchone()['total'] or 0
        saldo_kas = (masuk_siswa + masuk_lain) - pengeluaran
        
        jml_trx_siswa = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE status = 'Lunas'").fetchone()['total'] or 0
        jml_kas_masuk = db.execute("SELECT COUNT(*) as total FROM kas_masuk").fetchone()['total'] or 0
        jml_kas_keluar = db.execute("SELECT COUNT(*) as total FROM kas_keluar").fetchone()['total'] or 0
        total_transaksi = jml_trx_siswa + jml_kas_masuk + jml_kas_keluar

    elif role == 'tu':
        total_siswa = db.execute("SELECT COUNT(*) as total FROM siswa").fetchone()['total'] or 0
        total_tagihan_assign = db.execute("SELECT COUNT(*) as total FROM transaksi").fetchone()['total'] or 0
        total_menunggu_validasi = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE status = 'Menunggu Validasi'").fetchone()['total'] or 0

    elif role == 'walimurid':
        siswa = db.execute("SELECT id, nama FROM siswa WHERE nisn = ?", (username,)).fetchone()
        if siswa:
            nama_siswa_wm = siswa['nama']
            s_id = siswa['id']
            wm_belum_lunas = db.execute('''
                SELECT SUM(m.nominal) as total FROM transaksi t 
                JOIN master_tagihan m ON t.master_tagihan_id = m.id 
                WHERE t.siswa_id = ? AND t.status = 'Pending'
            ''', (s_id,)).fetchone()['total'] or 0
            wm_menunggu = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE siswa_id = ? AND status = 'Menunggu Validasi'", (s_id,)).fetchone()['total'] or 0
            wm_lunas = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE siswa_id = ? AND status = 'Lunas'", (s_id,)).fetchone()['total'] or 0

    return render_template('dashboard.html', 
                           role=role, username=username,
                           total_tagihan=total_tagihan, saldo_kas=saldo_kas, total_transaksi=total_transaksi,
                           total_siswa=total_siswa, total_tagihan_assign=total_tagihan_assign, total_menunggu_validasi=total_menunggu_validasi,
                           wm_belum_lunas=wm_belum_lunas, wm_menunggu=wm_menunggu, wm_lunas=wm_lunas, nama_siswa_wm=nama_siswa_wm)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==========================================
# 2. FITUR BENDAHARA & KEPSEK (Akses Penuh Rangkap Jabatan)
# ==========================================
@app.route('/bendahara/tagihan', methods=['GET', 'POST'])
def master_tagihan():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    # Kepsek & Bendahara sama-sama bisa menambah tagihan
    if request.method == 'POST':
        nama_tagihan = request.form.get('nama_tagihan')
        nominal = request.form.get('nominal')
        kategori = request.form.get('kategori')
        db.execute("INSERT INTO master_tagihan (nama_tagihan, nominal, kategori, is_active) VALUES (?, ?, ?, 1)", 
                   (nama_tagihan, nominal, kategori))
        db.commit()
        return redirect('/bendahara/tagihan')
            
    data_tagihan = db.execute("SELECT * FROM master_tagihan WHERE is_active = 1").fetchall()
    return render_template('bendahara_tagihan.html', tagihan=data_tagihan, role=session.get('role'), username=session.get('username'))

@app.route('/edit/tagihan/<int:id>', methods=['POST'])
def edit_tagihan(id):
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/bendahara/tagihan')
    db = get_db()
    nama_tagihan = request.form.get('nama_tagihan')
    nominal = request.form.get('nominal')
    db.execute("UPDATE master_tagihan SET nama_tagihan = ?, nominal = ? WHERE id = ?", (nama_tagihan, nominal, id))
    db.commit()
    return redirect('/bendahara/tagihan')

@app.route('/hapus/tagihan/<int:id>', methods=['POST'])
def hapus_tagihan(id):
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/bendahara/tagihan')
    db = get_db()
    # Tetap menggunakan Soft Delete agar riwayat transaksi aman
    db.execute("UPDATE master_tagihan SET is_active = 0 WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/tagihan')

@app.route('/bendahara/kas', methods=['GET', 'POST'])
def kelola_kas():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    # Kepsek & Bendahara sama-sama bisa mencatat kas baru
    if request.method == 'POST':
        jenis = request.form.get('jenis') 
        kategori_sumber = request.form.get('kategori_sumber')
        nominal = request.form.get('nominal')
        keterangan = request.form.get('keterangan')
        
        if jenis == 'masuk':
            db.execute("INSERT INTO kas_masuk (sumber, nominal, keterangan) VALUES (?, ?, ?)", (kategori_sumber, nominal, keterangan))
        elif jenis == 'keluar':
            db.execute("INSERT INTO kas_keluar (kategori, nominal, keterangan) VALUES (?, ?, ?)", (kategori_sumber, nominal, keterangan))
        db.commit()
        return redirect('/bendahara/kas')
        
    pemasukan_lain = db.execute("SELECT * FROM kas_masuk ORDER BY id DESC").fetchall()
    pengeluaran = db.execute("SELECT * FROM kas_keluar ORDER BY id DESC").fetchall()
    return render_template('bendahara_kas.html', masuk=pemasukan_lain, keluar=pengeluaran, role=session.get('role'), username=session.get('username'))

@app.route('/edit/kas_masuk/<int:id>', methods=['POST'])
def edit_kas_masuk(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/bendahara/kas')
    db = get_db()
    db.execute("UPDATE kas_masuk SET sumber = ?, nominal = ? WHERE id = ?", (request.form.get('sumber'), request.form.get('nominal'), id))
    db.commit()
    return redirect('/bendahara/kas')

@app.route('/hapus/kas_masuk/<int:id>', methods=['POST'])
def hapus_kas_masuk(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/bendahara/kas')
    db = get_db()
    db.execute("DELETE FROM kas_masuk WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/kas')

@app.route('/edit/kas_keluar/<int:id>', methods=['POST'])
def edit_kas_keluar(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/bendahara/kas')
    db = get_db()
    db.execute("UPDATE kas_keluar SET kategori = ?, nominal = ? WHERE id = ?", (request.form.get('kategori'), request.form.get('nominal'), id))
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
# --- UBAH PADA RUTE TU SISWA (TAMBAH & EDIT) ---
@app.route('/tu/siswa', methods=['GET', 'POST'])
def tu_siswa():
    if session.get('role') != 'tu':
        return redirect('/')
    
    db = get_db()
    if request.method == 'POST':
        nisn = request.form['nisn'].strip()
        nama = request.form['nama'].strip()
        hashed_pw = generate_password_hash(nisn)
        
        try:
            db.execute("INSERT INTO siswa (nisn, nama) VALUES (?, ?)", (nisn, nama))
            # Otomatis buat akun walimurid dengan nama siswa & username/password = NISN
            db.execute("INSERT INTO users (username, nama, password, role) VALUES (?, ?, ?, 'walimurid')", 
                       (nisn, nama, hashed_pw))
            db.commit()
        except sqlite3.IntegrityError:
            pass
        return redirect('/tu/siswa')
        
    siswa = db.execute("SELECT * FROM siswa ORDER BY nama ASC").fetchall()
    return render_template('tu_siswa.html', siswa=siswa, role=session.get('role'), username=session.get('username'))

@app.route('/edit/siswa/<int:id>', methods=['POST'])
def edit_siswa(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    siswa_lama = db.execute("SELECT nisn FROM siswa WHERE id = ?", (id,)).fetchone()
    nama_baru = request.form.get('nama').strip()
    nisn_baru = request.form.get('nisn').strip()
    
    if siswa_lama:
        db.execute("UPDATE siswa SET nama = ?, nisn = ? WHERE id = ?", (nama_baru, nisn_baru, id))
        # Sinkronisasi nama & NISN (username) di tabel users
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
        # Cascade delete agar tidak meninggalkan data yatim
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
        
        # Cek duplikasi tagihan pada siswa yang sama
        cek_duplikat = db.execute("SELECT id FROM transaksi WHERE siswa_id = ? AND master_tagihan_id = ?", 
                                  (siswa_id, tagihan_id)).fetchone()
        if cek_duplikat:
            pesan_error = "Tagihan tersebut sudah pernah diberikan kepada siswa ini!"
        else:
            db.execute("INSERT INTO transaksi (siswa_id, master_tagihan_id, status) VALUES (?, ?, 'Pending')", 
                       (siswa_id, tagihan_id))
            db.commit()
            return redirect('/tu/assign_tagihan')
        
    daftar_siswa = db.execute("SELECT id, nama, nisn FROM siswa ORDER BY nama ASC").fetchall()
    daftar_tagihan = db.execute("SELECT id, nama_tagihan, nominal FROM master_tagihan WHERE is_active = 1").fetchall()
    riwayat_tagihan = db.execute('''
        SELECT t.id, s.nama, m.nama_tagihan, m.nominal, t.status 
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

    # Daftar antrean menunggu validasi
    data_validasi = cursor.execute('''
        SELECT t.id, s.nama, s.nisn, m.nama_tagihan, m.nominal, t.metode_bayar, t.tanggal_bayar
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Menunggu Validasi'
        ORDER BY t.id ASC
    ''').fetchall()

    # Daftar riwayat lunas terbaru (untuk cetak PDF & kirim WA)
    riwayat_lunas = cursor.execute('''
        SELECT t.id, s.nama, s.nisn, m.nama_tagihan, m.nominal, t.metode_bayar, t.tanggal_validasi
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Lunas'
        ORDER BY t.tanggal_validasi DESC, t.id DESC
        LIMIT 15
    ''').fetchall()
    
    return render_template('tu_validasi.html', 
                           validasi=data_validasi, 
                           riwayat_lunas=riwayat_lunas,
                           role=session.get('role'), 
                           username=session.get('username'))

# ==========================================
# 4. FITUR WALI MURID (Anti-IDOR & Konfirmasi Metode ke WA TU)
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

    siswa = db.execute("SELECT id, nama FROM siswa WHERE nisn = ?", (nisn,)).fetchone()
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
                           nama_siswa=siswa['nama'], tagihan=tagihan_siswa,
                           role=session.get('role'), username=session.get('username'))

# ==========================================
# 5. LAPORAN & CETAK PDF
# ==========================================
@app.route('/laporan')
def laporan():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    masuk_siswa = db.execute("SELECT SUM(m.nominal) as total FROM transaksi t JOIN master_tagihan m ON t.master_tagihan_id = m.id WHERE t.status = 'Lunas'").fetchone()['total'] or 0
    masuk_lain = db.execute("SELECT SUM(nominal) as total FROM kas_masuk").fetchone()['total'] or 0
    total_pengeluaran = db.execute("SELECT SUM(nominal) as total FROM kas_keluar").fetchone()['total'] or 0
    
    total_pemasukan_semua = masuk_siswa + masuk_lain
    saldo_akhir = total_pemasukan_semua - total_pengeluaran

    rincian_masuk_lain = db.execute("SELECT * FROM kas_masuk ORDER BY id DESC").fetchall()
    rincian_pengeluaran = db.execute("SELECT * FROM kas_keluar ORDER BY id DESC").fetchall()
    
    return render_template('laporan.html', 
                           masuk_siswa=masuk_siswa, masuk_lain=masuk_lain,
                           total_masuk=total_pemasukan_semua, pengeluaran=total_pengeluaran,
                           saldo=saldo_akhir, rincian_masuk=rincian_masuk_lain, rincian_keluar=rincian_pengeluaran,
                           role=session.get('role'), username=session.get('username'))

@app.route('/laporan/pdf')
def cetak_pdf():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    
    total_pemasukan = db.execute("SELECT SUM(m.nominal) as total FROM transaksi t JOIN master_tagihan m ON t.master_tagihan_id = m.id WHERE t.status = 'Lunas'").fetchone()['total'] or 0
    rincian = db.execute('''
        SELECT t.id, s.nama, s.nisn, m.nama_tagihan, m.nominal, t.tanggal_validasi
        FROM transaksi t JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Lunas' ORDER BY t.id ASC
    ''').fetchall()

    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Laporan Pemasukan Pembayaran Siswa", ln=True, align="C")
    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 8, f"Dicetak pada: {datetime.now().strftime('%d-%m-%Y %H:%M')} | Total Pemasukan: Rp {total_pemasukan:,.0f}".replace(',', '.'), ln=True, align="C")
    pdf.ln(8) 
    
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(20, 10, "No. TRX", border=1)
    pdf.cell(50, 10, "Nama Siswa (NISN)", border=1)
    pdf.cell(55, 10, "Item Tagihan", border=1)
    pdf.cell(35, 10, "Tgl Validasi", border=1)
    pdf.cell(30, 10, "Nominal", border=1, ln=True)
    
    pdf.set_font("helvetica", "", 9)
    for r in rincian:
        tgl = str(r['tanggal_validasi'])[:10] if r['tanggal_validasi'] else "-"
        pdf.cell(20, 10, f"TRX-{r['id']}", border=1)
        pdf.cell(50, 10, f"{r['nama'][:14]} ({r['nisn']})", border=1)
        pdf.cell(55, 10, str(r['nama_tagihan'])[:25], border=1)
        pdf.cell(35, 10, tgl, border=1)
        pdf.cell(30, 10, f"Rp {r['nominal']:,.0f}".replace(',', '.'), border=1, ln=True)
        
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    
    return send_file(pdf_buffer, as_attachment=True, download_name="Laporan_Keuangan.pdf", mimetype="application/pdf")

@app.route('/invoice/pdf/<int:transaksi_id>')
def cetak_invoice_pdf(transaksi_id):
    role = session.get('role')
    username = session.get('username')
    if not role:
        return redirect('/')

    db = get_db()
    trx = db.execute('''
        SELECT t.id, t.status, t.metode_bayar, t.tanggal_validasi,
               s.nama AS nama_siswa, s.nisn,
               m.nama_tagihan, m.kategori, m.nominal
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.id = ?
    ''', (transaksi_id,)).fetchone()

    if not trx or trx['status'] != 'Lunas':
        return "<h3>Invoice tidak ditemukan atau transaksi belum lunas.</h3>"

    # Cegah wali murid mengunduh invoice milik siswa lain
    if role == 'walimurid' and trx['nisn'] != username:
        return redirect('/')

    pdf = FPDF(orientation='P', unit='mm', format='A5')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)

    # --- KOP SURAT INSTANSI YPI ARROJA ---
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 5, "YAYASAN PENDIDIKAN ISLAM ARROJA", ln=True, align="C")
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 5, "MADRASAH TSANAWIYAH & ALIYAH ARROJA", ln=True, align="C")
    
    pdf.set_font("helvetica", "", 7)
    pdf.cell(0, 4, "Jl. Garut - Tasik KM. 11 Kp. Cigarungsang, Ds. Mekarsari, Kec. Cilawu", ln=True, align="C")
    pdf.cell(0, 3.5, "Kab. Garut, Prov. Jawa Barat - 44181 | Telp: 082315467766", ln=True, align="C")
    pdf.cell(0, 3.5, "Email: mtsarroja@gmail.com & masarroja@gmail.com", ln=True, align="C")
    
    # Garis Kop Surat Ganda
    pdf.ln(2)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 138, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.line(10, pdf.get_y() + 1, 138, pdf.get_y() + 1)
    pdf.ln(5)

    # --- JUDUL DOKUMEN ---
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 6, "BUKTI PEMBAYARAN RESMI (INVOICE)", ln=True, align="C")
    pdf.set_font("helvetica", "", 9)
    no_inv = f"INV/{datetime.now().strftime('%Y%m')}/TRX-{trx['id']:04d}"
    pdf.cell(0, 5, f"Nomor Dokumen: {no_inv}", ln=True, align="C")
    pdf.ln(5)

    # --- DATA SISWA & TRANSAKSI ---
    pdf.set_font("helvetica", "", 9)
    tgl_val = str(trx['tanggal_validasi']) if trx['tanggal_validasi'] else datetime.now().strftime('%Y-%m-%d %H:%M')
    
    info_baris = [
        ("Nama Siswa", f": {trx['nama_siswa']}"),
        ("NISN", f": {trx['nisn']}"),
        ("Metode Bayar", f": {trx['metode_bayar'] or '-'}"),
        ("Waktu Validasi", f": {tgl_val}"),
    ]
    for label, val in info_baris:
        pdf.cell(35, 6, label, border=0)
        pdf.set_font("helvetica", "B" if label == "Nama Siswa" else "", 9)
        pdf.cell(0, 6, val, border=0, ln=True)
        pdf.set_font("helvetica", "", 9)

    pdf.ln(4)

    # --- TABEL RINCIAN PEMBAYARAN ---
    pdf.set_fill_color(230, 240, 255)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(68, 8, " Keterangan Tagihan", border=1, fill=True)
    pdf.cell(25, 8, " Kategori", border=1, fill=True, align="C")
    pdf.cell(35, 8, "Nominal ", border=1, fill=True, align="R", ln=True)

    pdf.set_font("helvetica", "", 9)
    nominal_str = f"Rp {trx['nominal']:,.0f}".replace(',', '.')
    pdf.cell(68, 9, f" {trx['nama_tagihan']}", border=1)
    pdf.cell(25, 9, f" {trx['kategori']}", border=1, align="C")
    pdf.cell(35, 9, f"{nominal_str} ", border=1, align="R", ln=True)

    # Baris Total
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(93, 8, " TOTAL DIBAYAR", border=1, fill=True)
    pdf.cell(35, 8, f"{nominal_str} ", border=1, fill=True, align="R", ln=True)

    pdf.ln(6)

    # --- STEMPEL STATUS LUNAS & TANDA TANGAN ---
    pdf.set_text_color(25, 135, 84) # Hijau
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(60, 10, "[ STATUS: LUNAS / SAH ]", border=1, align="C")
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 8)
    pdf.cell(68, 5, f"Divalidasi oleh Tata Usaha,", ln=True, align="R")
    pdf.ln(10)
    petugas = session.get('nama') if role in ['tu', 'bendahara', 'kepsek'] else "Staff Tata Usaha"
    pdf.set_font("helvetica", "B", 8)
    pdf.cell(0, 5, f"( {petugas} )", ln=True, align="R")

    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    nama_file = f"Invoice_{trx['nisn']}_{trx['nama_tagihan'].replace(' ', '_')}.pdf"
    return send_file(pdf_buffer, as_attachment=True, download_name=nama_file, mimetype="application/pdf")

if __name__ == '__main__':
    app.run(debug=True)