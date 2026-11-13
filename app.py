from flask import Flask, render_template, request, g, session, redirect
import sqlite3
from flask import send_file
from fpdf import FPDF
import io
import urllib.parse

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_ma_keuangan'  # Wajib ada untuk membaca/menyimpan session
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

# --- RUTE LOGIN (Menerima GET & POST) ---
@app.route('/', methods=['GET', 'POST'])
def login():
    # Jika sudah login, langsung lempar ke dashboard
    if session.get('role'):
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        
        if user:
            session['role'] = user['role']
            session['username'] = user['username']
            return redirect('/dashboard')
        else:
            return render_template('login.html', error="Username atau Password salah!")
            
    return render_template('login.html')

# --- RUTE DASHBOARD (Menerima GET & POST) ---
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('role'):
        return redirect('/')
        
    role = session.get('role')
    username = session.get('username')
    
    # Nilai default Kepsek/Bendahara
    total_tagihan = 0
    saldo_kas = 0
    total_transaksi = 0
    
    # Nilai default Staff TU
    total_siswa = 0
    total_tagihan_assign = 0
    total_menunggu_validasi = 0

    # Nilai default Walimurid
    wm_belum_lunas = 0
    wm_menunggu = 0
    wm_lunas = 0
    nama_siswa_wm = ""

    db = get_db()

    if role == 'kepsek':
        hasil_tagihan = db.execute("SELECT COUNT(*) as total FROM master_tagihan").fetchone()
        total_tagihan = hasil_tagihan['total'] if hasil_tagihan['total'] else 0
        
        masuk_siswa = db.execute("SELECT SUM(m.nominal) as total FROM transaksi t JOIN master_tagihan m ON t.master_tagihan_id = m.id WHERE t.status = 'Lunas'").fetchone()['total'] or 0
        masuk_lain = db.execute("SELECT SUM(nominal) as total FROM kas_masuk").fetchone()['total'] or 0
        pengeluaran = db.execute("SELECT SUM(nominal) as total FROM kas_keluar").fetchone()['total'] or 0
        saldo_kas = (masuk_siswa + masuk_lain) - pengeluaran
        
        jml_trx_siswa = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE status = 'Lunas'").fetchone()['total'] or 0
        jml_kas_masuk = db.execute("SELECT COUNT(*) as total FROM kas_masuk").fetchone()['total'] or 0
        jml_kas_keluar = db.execute("SELECT COUNT(*) as total FROM kas_keluar").fetchone()['total'] or 0
        total_transaksi = jml_trx_siswa + jml_kas_masuk + jml_kas_keluar

    elif role == 'tu':
        hasil_siswa = db.execute("SELECT COUNT(*) as total FROM siswa").fetchone()
        total_siswa = hasil_siswa['total'] if hasil_siswa['total'] else 0
        
        hasil_assign = db.execute("SELECT COUNT(*) as total FROM transaksi").fetchone()
        total_tagihan_assign = hasil_assign['total'] if hasil_assign['total'] else 0
        
        hasil_validasi = db.execute("SELECT COUNT(*) as total FROM transaksi WHERE status = 'Menunggu Validasi'").fetchone()
        total_menunggu_validasi = hasil_validasi['total'] if hasil_validasi['total'] else 0

    elif role == 'walimurid':
        siswa = db.execute("SELECT id, nama FROM siswa WHERE nisn = ?", (username,)).fetchone()
        if siswa:
            nama_siswa_wm = siswa['nama']
            s_id = siswa['id']
            
            # 1. Total Nominal Tagihan Pending (Belum Lunas)
            wm_belum_lunas = db.execute('''
                SELECT SUM(m.nominal) as total FROM transaksi t 
                JOIN master_tagihan m ON t.master_tagihan_id = m.id 
                WHERE t.siswa_id = ? AND t.status = 'Pending'
            ''', (s_id,)).fetchone()['total'] or 0

            # 2. Jumlah Tagihan Menunggu Validasi
            wm_menunggu = db.execute('''
                SELECT COUNT(*) as total FROM transaksi 
                WHERE siswa_id = ? AND status = 'Menunggu Validasi'
            ''', (s_id,)).fetchone()['total'] or 0

            # 3. Jumlah Tagihan Sudah Lunas
            wm_lunas = db.execute('''
                SELECT COUNT(*) as total FROM transaksi 
                WHERE siswa_id = ? AND status = 'Lunas'
            ''', (s_id,)).fetchone()['total'] or 0

    return render_template('dashboard.html', 
                           role=role, 
                           username=username,
                           total_tagihan=total_tagihan,
                           saldo_kas=saldo_kas,
                           total_transaksi=total_transaksi,
                           total_siswa=total_siswa,
                           total_tagihan_assign=total_tagihan_assign,
                           total_menunggu_validasi=total_menunggu_validasi,
                           wm_belum_lunas=wm_belum_lunas,
                           wm_menunggu=wm_menunggu,
                           wm_lunas=wm_lunas,
                           nama_siswa_wm=nama_siswa_wm)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/tu/siswa', methods=['GET', 'POST'])
def tu_siswa():
    if session.get('role') != 'tu':
        return redirect('/')
    
    db = get_db()
    if request.method == 'POST':
        nisn = request.form['nisn']
        nama = request.form['nama']
        
        try:
            db.execute("INSERT INTO siswa (nisn, nama) VALUES (?, ?)", (nisn, nama))
            db.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'walimurid')", (nisn, nisn))
            db.commit()
        except sqlite3.IntegrityError:
            pass
            
        return redirect('/tu/siswa')
        
    siswa = db.execute("SELECT * FROM siswa").fetchall()
    return render_template('tu_siswa.html', siswa=siswa)

@app.route('/bendahara/tagihan', methods=['GET', 'POST'])
def master_tagihan():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        nama_tagihan = request.form.get('nama_tagihan')
        nominal = request.form.get('nominal')
        kategori = request.form.get('kategori')
        
        cursor.execute("INSERT INTO master_tagihan (nama_tagihan, nominal, kategori) VALUES (?, ?, ?)", 
                       (nama_tagihan, nominal, kategori))
        db.commit()
            
    cursor.execute("SELECT * FROM master_tagihan")
    data_tagihan = cursor.fetchall()
    return render_template('bendahara_tagihan.html', tagihan=data_tagihan)

@app.route('/tu/assign_tagihan', methods=['GET', 'POST'])
def assign_tagihan():
    if session.get('role') != 'tu':
        return redirect('/')
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        siswa_id = request.form.get('siswa_id')
        tagihan_id = request.form.get('tagihan_id')
        
        cursor.execute("INSERT INTO transaksi (siswa_id, master_tagihan_id, status) VALUES (?, ?, 'Pending')", 
                       (siswa_id, tagihan_id))
        db.commit()
        
    cursor.execute("SELECT id, nama, nisn FROM siswa")
    daftar_siswa = cursor.fetchall()
    
    cursor.execute("SELECT id, nama_tagihan, nominal FROM master_tagihan")
    daftar_tagihan = cursor.fetchall()
    
    cursor.execute('''
        SELECT t.id, s.nama, m.nama_tagihan, m.nominal, t.status 
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        ORDER BY t.id DESC
    ''')
    riwayat_tagihan = cursor.fetchall()
    
    return render_template('tu_assign_tagihan.html', 
                           siswa=daftar_siswa, 
                           tagihan=daftar_tagihan, 
                           riwayat=riwayat_tagihan)

@app.route('/walimurid/tagihan/<nisn>', methods=['GET', 'POST'])
def walimurid_tagihan(nisn):
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        transaksi_id = request.form.get('transaksi_id')
        metode_bayar = request.form.get('metode_bayar')
        
        cursor.execute("UPDATE transaksi SET status = 'Menunggu Validasi', metode_bayar = ? WHERE id = ?", 
                       (metode_bayar, transaksi_id))
        db.commit()

    cursor.execute("SELECT id, nama FROM siswa WHERE nisn = ?", (nisn,))
    siswa = cursor.fetchone()
    
    if not siswa:
        return "<h3>Data siswa tidak ditemukan. Silakan lapor ke TU.</h3>"
        
    cursor.execute('''
        SELECT t.id, m.nama_tagihan, m.nominal, t.status
        FROM transaksi t
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.siswa_id = ?
        ORDER BY t.id DESC
    ''', (siswa['id'],))
    tagihan_siswa = cursor.fetchall()
    
    return render_template('walimurid_tagihan.html', 
                           nama_siswa=siswa['nama'], 
                           tagihan=tagihan_siswa)

# @app.route('/tu/validasi', methods=['GET', 'POST'])
# def tu_validasi():
#     if session.get('role') != 'tu':
#         return redirect('/')
#     db = get_db()
#     cursor = db.cursor()
    
#     if request.method == 'POST':
#         transaksi_id = request.form.get('transaksi_id')
#         aksi = request.form.get('aksi')
        
#         if aksi == 'Terima':
#             cursor.execute("UPDATE transaksi SET status = 'Lunas' WHERE id = ?", (transaksi_id,))
#         elif aksi == 'Tolak':
#             cursor.execute("UPDATE transaksi SET status = 'Pending' WHERE id = ?", (transaksi_id,))
#         db.commit()

#     cursor.execute('''
#         SELECT t.id, s.nama, s.nisn, m.nama_tagihan, m.nominal, t.metode_bayar
#         FROM transaksi t
#         JOIN siswa s ON t.siswa_id = s.id
#         JOIN master_tagihan m ON t.master_tagihan_id = m.id
#         WHERE t.status = 'Menunggu Validasi'
#         ORDER BY t.id ASC
#     ''')
#     data_validasi = cursor.fetchall()
    
#     return render_template('tu_validasi.html', validasi=data_validasi)

@app.route('/laporan')
def laporan():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT SUM(m.nominal) as total FROM transaksi t JOIN master_tagihan m ON t.master_tagihan_id = m.id WHERE t.status = 'Lunas'")
    masuk_siswa = cursor.fetchone()['total'] or 0
    
    cursor.execute("SELECT SUM(nominal) as total FROM kas_masuk")
    masuk_lain = cursor.fetchone()['total'] or 0
    
    cursor.execute("SELECT SUM(nominal) as total FROM kas_keluar")
    total_pengeluaran = cursor.fetchone()['total'] or 0
    
    total_pemasukan_semua = masuk_siswa + masuk_lain
    saldo_akhir = total_pemasukan_semua - total_pengeluaran

    cursor.execute("SELECT * FROM kas_masuk ORDER BY id DESC")
    rincian_masuk_lain = cursor.fetchall()
    
    cursor.execute("SELECT * FROM kas_keluar ORDER BY id DESC")
    rincian_pengeluaran = cursor.fetchall()
    
    return render_template('laporan.html', 
                           masuk_siswa=masuk_siswa, 
                           masuk_lain=masuk_lain,
                           total_masuk=total_pemasukan_semua,
                           pengeluaran=total_pengeluaran,
                           saldo=saldo_akhir,
                           rincian_masuk=rincian_masuk_lain,
                           rincian_keluar=rincian_pengeluaran)

@app.route('/laporan/pdf')
def cetak_pdf():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT SUM(m.nominal) as total FROM transaksi t JOIN master_tagihan m ON t.master_tagihan_id = m.id WHERE t.status = 'Lunas'")
    total_pemasukan = cursor.fetchone()['total'] or 0
        
    cursor.execute('''
        SELECT t.id, s.nama, s.nisn, m.nama_tagihan, m.nominal
        FROM transaksi t JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Lunas' ORDER BY t.id ASC
    ''')
    rincian = cursor.fetchall()

    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Laporan Pemasukan Keuangan Sekolah", ln=True, align="C")
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"Total Pemasukan: Rp {total_pemasukan:,.0f}".replace(',', '.'), ln=True, align="C")
    pdf.ln(10) 
    
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(20, 10, "No. TRX", border=1)
    pdf.cell(60, 10, "Nama Siswa (NISN)", border=1)
    pdf.cell(80, 10, "Item Tagihan", border=1)
    pdf.cell(30, 10, "Nominal", border=1, ln=True)
    
    pdf.set_font("helvetica", "", 10)
    for r in rincian:
        pdf.cell(20, 10, f"TRX-{r['id']}", border=1)
        pdf.cell(60, 10, f"{r['nama'][:15]} ({r['nisn']})", border=1)
        pdf.cell(80, 10, str(r['nama_tagihan']), border=1)
        pdf.cell(30, 10, f"Rp {r['nominal']:,.0f}".replace(',', '.'), border=1, ln=True)
        
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    
    return send_file(pdf_buffer, as_attachment=True, download_name="Laporan_Keuangan.pdf", mimetype="application/pdf")

@app.route('/bendahara/kas', methods=['GET', 'POST'])
def kelola_kas():
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        jenis = request.form.get('jenis') 
        kategori_sumber = request.form.get('kategori_sumber')
        nominal = request.form.get('nominal')
        keterangan = request.form.get('keterangan')
        
        if jenis == 'masuk':
            cursor.execute("INSERT INTO kas_masuk (sumber, nominal, keterangan) VALUES (?, ?, ?)", (kategori_sumber, nominal, keterangan))
        elif jenis == 'keluar':
            cursor.execute("INSERT INTO kas_keluar (kategori, nominal, keterangan) VALUES (?, ?, ?)", (kategori_sumber, nominal, keterangan))
        db.commit()
        
    cursor.execute("SELECT * FROM kas_masuk ORDER BY id DESC")
    pemasukan_lain = cursor.fetchall()
    
    cursor.execute("SELECT * FROM kas_keluar ORDER BY id DESC")
    pengeluaran = cursor.fetchall()
    
    return render_template('bendahara_kas.html', masuk=pemasukan_lain, keluar=pengeluaran)

@app.route('/hapus/tagihan/<int:id>')
def hapus_tagihan(id):
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    db.execute("DELETE FROM master_tagihan WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/tagihan')

@app.route('/hapus/kas_masuk/<int:id>')
def hapus_kas_masuk(id):
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    db.execute("DELETE FROM kas_masuk WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/kas')

@app.route('/hapus/kas_keluar/<int:id>')
def hapus_kas_keluar(id):
    if session.get('role') not in ['kepsek', 'bendahara']:
        return redirect('/')
    db = get_db()
    db.execute("DELETE FROM kas_keluar WHERE id = ?", (id,))
    db.commit()
    return redirect('/bendahara/kas')

# ==========================================
# FITUR UPDATE & DELETE (CRUD LENGKAP)
# ==========================================

# --- CRUD SISWA ---
@app.route('/hapus/siswa/<int:id>')
def hapus_siswa(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    db.execute("DELETE FROM siswa WHERE id = ?", (id,))
    db.commit()
    return redirect('/tu/siswa')

@app.route('/edit/siswa/<int:id>', methods=['POST'])
def edit_siswa(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    nama = request.form.get('nama')
    nisn = request.form.get('nisn')
    db.execute("UPDATE siswa SET nama = ?, nisn = ? WHERE id = ?", (nama, nisn, id))
    db.commit()
    return redirect('/tu/siswa')

# --- CRUD TRANSAKSI TAGIHAN SISWA ---
@app.route('/hapus/transaksi/<int:id>')
def hapus_transaksi(id):
    if session.get('role') != 'tu': return redirect('/')
    db = get_db()
    db.execute("DELETE FROM transaksi WHERE id = ?", (id,))
    db.commit()
    return redirect('/tu/assign_tagihan')

# --- CRUD MASTER TAGIHAN ---
@app.route('/edit/tagihan/<int:id>', methods=['POST'])
def edit_tagihan(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/')
    db = get_db()
    nama_tagihan = request.form.get('nama_tagihan')
    nominal = request.form.get('nominal')
    db.execute("UPDATE master_tagihan SET nama_tagihan = ?, nominal = ? WHERE id = ?", (nama_tagihan, nominal, id))
    db.commit()
    return redirect('/bendahara/tagihan')

# --- CRUD KAS MASUK & KELUAR ---
@app.route('/edit/kas_masuk/<int:id>', methods=['POST'])
def edit_kas_masuk(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/')
    db = get_db()
    sumber = request.form.get('sumber')
    nominal = request.form.get('nominal')
    db.execute("UPDATE kas_masuk SET sumber = ?, nominal = ? WHERE id = ?", (sumber, nominal, id))
    db.commit()
    return redirect('/bendahara/kas')

@app.route('/edit/kas_keluar/<int:id>', methods=['POST'])
def edit_kas_keluar(id):
    if session.get('role') not in ['kepsek', 'bendahara']: return redirect('/')
    db = get_db()
    kategori = request.form.get('kategori')
    nominal = request.form.get('nominal')
    db.execute("UPDATE kas_keluar SET kategori = ?, nominal = ? WHERE id = ?", (kategori, nominal, id))
    db.commit()
    return redirect('/bendahara/kas')

@app.route('/tu/validasi', methods=['GET', 'POST'])
def tu_validasi():
    # Pastikan user yang login adalah Staff TU
    if session.get('role') != 'tu':
        return redirect('/')

    db = get_db()
    cursor = db.cursor()

    # JIKA ADA PENGIRIMAN DATA (Tombol Terima/Tolak diklik)
    if request.method == 'POST':
        transaksi_id = request.form.get('transaksi_id')
        aksi = request.form.get('aksi')
        no_wa = request.form.get('no_wa')

        if aksi == 'Terima':
            cursor.execute("UPDATE transaksi SET status = 'Lunas' WHERE id = ?", (transaksi_id,))
            db.commit()

            # Jika Staff TU memasukkan nomor WA, buatkan link invoice WhatsApp
            if no_wa and no_wa.strip() != "":
                # Ambil detail transaksi dengan JOIN yang benar
                cursor.execute('''
                    SELECT s.nama, s.nisn, m.nama_tagihan, m.nominal 
                    FROM transaksi t 
                    JOIN siswa s ON t.siswa_id = s.id 
                    JOIN master_tagihan m ON t.master_tagihan_id = m.id
                    WHERE t.id = ?
                ''', (transaksi_id,))
                data = cursor.fetchone()

                if data:
                    if no_wa.startswith('0'):
                        no_wa = '62' + no_wa[1:]

                    nominal_rp = f"Rp {{:,.0f}}".format(data['nominal']).replace(',', '.')
                    pesan = f"🧾 *INVOICE PEMBAYARAN LUNAS*\n\n"
                    pesan += f"Terima kasih, pembayaran berikut telah kami terima dan divalidasi oleh Tata Usaha:\n\n"
                    pesan += f"👤 *Nama*: {data['nama']}\n"
                    pesan += f"🆔 *NISN*: {data['nisn']}\n"
                    pesan += f"📝 *Item*: {data['nama_tagihan']}\n"
                    pesan += f"💰 *Nominal*: {nominal_rp}\n\n"
                    pesan += f"Mohon simpan pesan ini sebagai bukti pembayaran yang sah."

                    pesan_encoded = urllib.parse.quote(pesan)
                    return redirect(f"https://wa.me/{no_wa}?text={pesan_encoded}")

        elif aksi == 'Tolak':
            # Jika ditolak, kembalikan status menjadi Pending / Belum Lunas
            cursor.execute("UPDATE transaksi SET status = 'Pending' WHERE id = ?", (transaksi_id,))
            db.commit()

        # Jika sukses tanpa nomor WA, atau jika ditolak, kembali muat ulang tabel
        return redirect('/tu/validasi')

    # JIKA HANYA MEMBUKA HALAMAN (GET)
    cursor.execute('''
        SELECT t.id, s.nama, s.nisn, m.nama_tagihan, m.nominal, t.metode_bayar
        FROM transaksi t
        JOIN siswa s ON t.siswa_id = s.id
        JOIN master_tagihan m ON t.master_tagihan_id = m.id
        WHERE t.status = 'Menunggu Validasi'
        ORDER BY t.id ASC
    ''')
    data_validasi = cursor.fetchall()
    
    return render_template('tu_validasi.html', validasi=data_validasi)

if __name__ == '__main__':
    app.run(debug=True)