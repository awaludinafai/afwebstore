from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename

import os

base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

app.secret_key = 'afweb_code_private_key_2026'

UPLOAD_FOLDER = os.path.join(base_dir, 'static/uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    db_path = os.path.join(base_dir, 'acode_pos.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def delete_file_if_exists(db_path):
    if not db_path: return
    if db_path.startswith('/'): db_path = db_path[1:]
    abs_path = os.path.join(base_dir, db_path.replace('/', os.sep))
    if os.path.exists(abs_path):
        try: os.remove(abs_path)
        except: pass

def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS barang (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama TEXT NOT NULL, stok INTEGER NOT NULL,
                    harga REAL NOT NULL, foto TEXT)''')
    
    # PERUBAHAN: Menambahkan kolom bukti_pembayaran jika belum ada
    db.execute('''CREATE TABLE IF NOT EXISTS transaksi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_list TEXT, json_items TEXT, total_harga REAL,
                    metode TEXT, alamat TEXT, no_hp TEXT,
                    bukti_pembayaran TEXT,
                    status TEXT DEFAULT 'Pending',
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                    
    db.execute('''CREATE TABLE IF NOT EXISTS pelamar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama TEXT, email TEXT, posisi TEXT, kontak TEXT, cv_path TEXT,
                    status TEXT DEFAULT 'Pending',
                    waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                    
    db.execute('''CREATE TABLE IF NOT EXISTS biodata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pelamar_id INTEGER,
                    nama_lengkap TEXT, tempat_lahir TEXT, agama TEXT, kewarganegaraan TEXT, status_kawin TEXT, no_telp TEXT,
                    nik TEXT, alamat_lengkap TEXT, 
                    tgl_lahir TEXT, pendidikan_terakhir TEXT,
                    foto_ktp TEXT, foto_wajah TEXT,
                    waktu_isi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(pelamar_id) REFERENCES pelamar(id))''')
                    
    columns_to_add = [
        "foto_ktp TEXT", "foto_wajah TEXT", "nama_lengkap TEXT",
        "tempat_lahir TEXT", "agama TEXT", "kewarganegaraan TEXT",
        "status_kawin TEXT", "no_telp TEXT", "foto_ijazah TEXT"
    ]
    for col in columns_to_add:
        try:
            db.execute(f"ALTER TABLE biodata ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    
    # FITUR BARU: Tabel Settings untuk simpan QRIS dan Rekening
    db.execute('''CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY,
                    rekening TEXT,
                    qris_path TEXT)''')
    
    # Tambahkan kolom diskon dan banner
    columns_to_add_settings = [
        "diskon INTEGER DEFAULT 0", "banner_aktif INTEGER DEFAULT 0", "banner_text TEXT DEFAULT ''"
    ]
    for col in columns_to_add_settings:
        try:
            db.execute(f"ALTER TABLE settings ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    
    admin_exists = db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    if not admin_exists:
        db.execute("INSERT INTO users (username, password, role) VALUES ('admin', ?, 'admin')", (generate_password_hash('admin123'),))
        db.execute("INSERT INTO users (username, password, role) VALUES ('kasir', ?, 'kasir')", (generate_password_hash('kasir123'),))
    
    # Migrasi otomatis password teks asli menjadi hash
    all_users = db.execute("SELECT id, password FROM users").fetchall()
    for u in all_users:
        if not u['password'].startswith('scrypt:') and not u['password'].startswith('pbkdf2:'):
            db.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(u['password']), u['id']))
    
    # Inisialisasi default settings jika kosong
    setting_exists = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if not setting_exists:
        db.execute("INSERT INTO settings (id, rekening, qris_path) VALUES (1, 'Silakan atur nomor rekening di admin.', '')")
    
    db.commit()
    db.close()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/isi-biodata')
def isi_biodata_page():
    return render_template('isi-biodata.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
        if user and check_password_hash(user['password'], p):
            session['user_role'] = user['role']
            session['username'] = user['username']
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error="Username atau password salah")
    return render_template('login.html')

@app.route('/admin')
def admin():
    if 'user_role' not in session: return redirect(url_for('login'))
    return render_template('admin.html', role=session['user_role'], username=session.get('username'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- API SETTINGS PEMBAYARAN & TOKO ---
@app.route('/api/settings/pembayaran', methods=['GET', 'POST'])
def manage_settings():
    db = get_db()
    if request.method == 'POST':
        if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
        rekening = request.form.get('rekening')
        diskon = request.form.get('diskon')
        banner_aktif = request.form.get('banner_aktif')
        banner_text = request.form.get('banner_text')
        file_qris = request.files.get('qris')
        
        db.execute("UPDATE settings SET rekening=?, diskon=?, banner_aktif=?, banner_text=? WHERE id=1", 
                   (rekening, diskon or 0, banner_aktif or 0, banner_text or ''))
                   
        if file_qris:
            fname = secure_filename(f"QRIS_{file_qris.filename}")
            file_qris.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            db.execute("UPDATE settings SET qris_path = ? WHERE id = 1", (f"/static/uploads/{fname}",))
        db.commit()
        return jsonify({"status": "success"})
    row = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return jsonify(dict(row))

# --- API BACKUP & CLEAN APP ---
@app.route('/api/backup', methods=['GET'])
def backup_db():
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    db_path = os.path.join(base_dir, 'acode_pos.db')
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True, download_name=f"Backup_AFWEB_{datetime.now().strftime('%Y%m%d_%H%M')}.db")
    return jsonify({"status": "error", "message": "File not found"}), 404

@app.route('/api/clean', methods=['POST'])
def clean_app():
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    data = request.json
    db = get_db()
    if data.get('pesanan'):
        t_files = db.execute("SELECT bukti_pembayaran FROM transaksi").fetchall()
        for t in t_files: delete_file_if_exists(t['bukti_pembayaran'])
        db.execute("DELETE FROM transaksi")
    if data.get('pelamar'):
        b_files = db.execute("SELECT foto_ktp, foto_wajah, foto_ijazah FROM biodata").fetchall()
        for bf in b_files:
            delete_file_if_exists(bf['foto_ktp'])
            delete_file_if_exists(bf['foto_wajah'])
            delete_file_if_exists(bf['foto_ijazah'])
        p_files = db.execute("SELECT cv_path FROM pelamar").fetchall()
        for pf in p_files: delete_file_if_exists(pf['cv_path'])
        db.execute("DELETE FROM pelamar")
        db.execute("DELETE FROM biodata")
    if data.get('barang'):
        b_files = db.execute("SELECT foto FROM barang").fetchall()
        for b in b_files:
            if b['foto']:
                try:
                    for f in json.loads(b['foto']): delete_file_if_exists(f)
                except: pass
        db.execute("DELETE FROM barang")
    db.commit()
    return jsonify({"status": "success", "message": "Data berhasil dibersihkan."})

@app.route('/api/users', methods=['GET', 'POST'])
def api_users():
    if session.get('user_role') != 'admin': return jsonify([]), 403
    db = get_db()
    if request.method == 'POST':
        d = request.json
        try:
            hashed_pw = generate_password_hash(d['password'])
            db.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (d['username'], hashed_pw, d['role']))
            db.commit()
            return jsonify({"status": "success"})
        except:
            return jsonify({"status": "error", "message": "Username sudah ada!"}), 400
    rows = db.execute("SELECT id, username, role FROM users").fetchall()
    return jsonify([dict(row) for row in rows])

@app.route('/api/users/delete/<int:id>', methods=['POST'])
def delete_user(id):
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ? AND username != 'admin'", (id,))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/users/update', methods=['POST'])
def update_user():
    if session.get('user_role') != 'admin': 
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    db = get_db()
    data = request.json
    uid, username, password, role = data.get('id'), data.get('username'), data.get('password'), data.get('role')
    db.execute("UPDATE users SET username=?, role=? WHERE id=?", (username, role, uid))
    if password:
        hashed_pw = generate_password_hash(password)
        db.execute("UPDATE users SET password=? WHERE id=?", (hashed_pw, uid))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/barang', methods=['GET', 'POST'])
def api_barang():
    db = get_db()
    if request.method == 'POST':
        if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
        nama, stok, harga = request.form.get('nama'), request.form.get('stok'), request.form.get('harga')
        files = request.files.getlist('foto[]')
        foto_paths = []
        for file in files:
            if file.filename:
                fname = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                foto_paths.append(f"/static/uploads/{fname}")
        
        foto_path_str = json.dumps(foto_paths) if foto_paths else "[]"
        db.execute("INSERT INTO barang (nama, stok, harga, foto) VALUES (?,?,?,?)", (nama, stok, harga, foto_path_str))
        db.commit()
        return jsonify({"status": "success"})
    return jsonify([dict(row) for row in db.execute("SELECT * FROM barang").fetchall()])

@app.route('/api/barang/update', methods=['POST'])
def update_barang():
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    db = get_db()
    id, nama, stok, harga = request.form.get('id'), request.form.get('nama'), request.form.get('stok'), request.form.get('harga')
    db.execute("UPDATE barang SET nama=?, stok=?, harga=? WHERE id=?", (nama, stok, harga, id))
    
    files = request.files.getlist('foto[]')
    foto_paths = []
    for file in files:
        if file.filename:
            fname = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            foto_paths.append(f"/static/uploads/{fname}")
            
    if foto_paths:
        db.execute("UPDATE barang SET foto=? WHERE id=?", (json.dumps(foto_paths), id))
    
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/barang/delete/<int:id>', methods=['POST'])
def delete_barang(id):
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    db = get_db()
    db.execute("DELETE FROM barang WHERE id = ?", (id,))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/lamar', methods=['POST'])
def api_lamar():
    try:
        nama, email, posisi, kontak = request.form.get('nama'), request.form.get('email'), request.form.get('posisi'), request.form.get('kontak')
        file = request.files.get('cv')
        cv_url = ""
        if file:
            filename = f"CV_{nama}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cv_url = f"/static/uploads/{filename}"
        db = get_db()
        db.execute("INSERT INTO pelamar (nama, email, posisi, kontak, cv_path, status) VALUES (?,?,?,?,?,?)", 
                    (nama, email, posisi, kontak, cv_url, 'Pending'))
        db.commit()
        return jsonify({"status": "success", "message": "Lamaran Anda telah terkirim!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/biodata/submit', methods=['POST'])
def submit_biodata():
    db = get_db()
    pelamar_id = request.form.get('pelamar_id')
    nama_lengkap = request.form.get('nama_lengkap')
    tempat_lahir = request.form.get('tempat_lahir')
    agama = request.form.get('agama')
    kewarganegaraan = request.form.get('kewarganegaraan')
    status_kawin = request.form.get('status_kawin')
    no_telp = request.form.get('no_telp')
    nik = request.form.get('nik')
    alamat = request.form.get('alamat')
    tgl_lahir = request.form.get('tgl_lahir')
    pendidikan = request.form.get('pendidikan')
    
    file_ktp = request.files.get('foto_ktp')
    file_wajah = request.files.get('foto_wajah')
    file_ijazah = request.files.get('foto_ijazah')
    
    foto_ktp_path = ""
    if file_ktp:
        fname = secure_filename(f"KTP_{pelamar_id}_{file_ktp.filename}")
        file_ktp.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        foto_ktp_path = f"/static/uploads/{fname}"
        
    foto_wajah_path = ""
    if file_wajah:
        fname = secure_filename(f"WAJAH_{pelamar_id}_{file_wajah.filename}")
        file_wajah.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        foto_wajah_path = f"/static/uploads/{fname}"

    foto_ijazah_path = ""
    if file_ijazah:
        fname = secure_filename(f"IJAZAH_{pelamar_id}_{file_ijazah.filename}")
        file_ijazah.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        foto_ijazah_path = f"/static/uploads/{fname}"

    db.execute("INSERT INTO biodata (pelamar_id, nama_lengkap, tempat_lahir, agama, kewarganegaraan, status_kawin, no_telp, nik, alamat_lengkap, tgl_lahir, pendidikan_terakhir, foto_ktp, foto_wajah, foto_ijazah) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pelamar_id, nama_lengkap, tempat_lahir, agama, kewarganegaraan, status_kawin, no_telp, nik, alamat, tgl_lahir, pendidikan, foto_ktp_path, foto_wajah_path, foto_ijazah_path))
    db.execute("UPDATE pelamar SET status = 'Biodata Lengkap' WHERE id = ?", (pelamar_id,))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/biodata/<int:pelamar_id>')
def get_biodata(pelamar_id):
    if session.get('user_role') != 'admin': return jsonify({}), 403
    db = get_db()
    row = db.execute("SELECT * FROM biodata WHERE pelamar_id = ?", (pelamar_id,)).fetchone()
    return jsonify(dict(row) if row else {})

@app.route('/api/biodata/detail/<int:id>')
def get_biodata_detail(id):
    if session.get('user_role') != 'admin': return jsonify({}), 403
    db = get_db()
    row = db.execute("SELECT * FROM biodata WHERE id = ?", (id,)).fetchone()
    return jsonify(dict(row) if row else {})

@app.route('/api/biodata/all')
def get_all_biodata():
    if session.get('user_role') != 'admin': return jsonify([]), 403
    db = get_db()
    rows = db.execute('''
        SELECT b.*, p.nama AS pelamar_nama, p.posisi AS pelamar_posisi
        FROM biodata b
        LEFT JOIN pelamar p ON b.pelamar_id = p.id
        ORDER BY b.id DESC
    ''').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/biodata/delete/<int:id>', methods=['POST'])
def delete_biodata(id):
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    db = get_db()
    row = db.execute("SELECT pelamar_id, foto_ktp, foto_wajah, foto_ijazah FROM biodata WHERE id = ?", (id,)).fetchone()
    if row:
        delete_file_if_exists(row['foto_ktp'])
        delete_file_if_exists(row['foto_wajah'])
        delete_file_if_exists(row['foto_ijazah'])
        db.execute("DELETE FROM biodata WHERE id = ?", (id,))
        # Reset status pelamar ke Interview jika biodata dihapus (karena sudah lolos CV)
        db.execute("UPDATE pelamar SET status = 'Interview' WHERE id = ?", (row['pelamar_id'],))
        db.commit()
    return jsonify({"status": "success"})

@app.route('/api/pelamar/delete/<int:id>', methods=['POST'])
def delete_pelamar(id):
    if session.get('user_role') != 'admin': return jsonify({"status": "error"}), 403
    db = get_db()
    p_row = db.execute("SELECT cv_path FROM pelamar WHERE id = ?", (id,)).fetchone()
    if p_row: delete_file_if_exists(p_row['cv_path'])
    
    b_rows = db.execute("SELECT foto_ktp, foto_wajah, foto_ijazah FROM biodata WHERE pelamar_id = ?", (id,)).fetchall()
    for row in b_rows:
        delete_file_if_exists(row['foto_ktp'])
        delete_file_if_exists(row['foto_wajah'])
        delete_file_if_exists(row['foto_ijazah'])
        
    db.execute("DELETE FROM pelamar WHERE id = ?", (id,))
    db.execute("DELETE FROM biodata WHERE pelamar_id = ?", (id,))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/pelamar', methods=['GET', 'POST'])
def manage_pelamar():
    if session.get('user_role') != 'admin': return jsonify([]), 403
    db = get_db()
    if request.method == 'POST':
        d = request.json
        db.execute("UPDATE pelamar SET status = ? WHERE id = ?", (d['status'], d['id']))
        db.commit()
        return jsonify({"status": "success"})
    rows = db.execute("SELECT * FROM pelamar ORDER BY waktu DESC").fetchall()
    return jsonify([dict(row) for row in rows])

# --- PERBAIKAN API CHECKOUT (SUPPORT UPLOAD BUKTI) ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    db = get_db()
    # Menangkap data dari FormData
    items_json = request.form.get('items')
    items_list = json.loads(items_json)
    metode = request.form.get('metode')
    total = request.form.get('total')
    alamat = request.form.get('alamat')
    no_hp = request.form.get('no_hp')
    
    items_str = ", ".join([f"{i['nama']} ({i['qty']})" for i in items_list])
    
    # Simpan Bukti Pembayaran jika ada
    bukti_path = ""
    file_bukti = request.files.get('bukti')
    if file_bukti:
        fname = secure_filename(f"BUKTI_{no_hp}_{file_bukti.filename}")
        file_bukti.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        bukti_path = f"/static/uploads/{fname}"

    db.execute('''INSERT INTO transaksi 
                  (item_list, json_items, total_harga, metode, alamat, no_hp, bukti_pembayaran, status) 
                  VALUES (?,?,?,?,?,?,?,?)''',
               (items_str, items_json, total, metode, alamat, no_hp, bukti_path, 'Pending'))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/order/action', methods=['POST'])
def order_action():
    d = request.json
    db = get_db()
    if d['action'] == 'Selesai':
        order = db.execute("SELECT json_items FROM transaksi WHERE id = ?", (d['id'],)).fetchone()
        for i in json.loads(order['json_items']):
            db.execute("UPDATE barang SET stok = stok - ? WHERE id = ?", (i['qty'], i['id']))
        db.execute("UPDATE transaksi SET status = 'Selesai' WHERE id = ?", (d['id'],))
    elif d['action'] == 'Batalkan':
        db.execute("UPDATE transaksi SET status = 'Dibatalkan' WHERE id = ?", (d['id'],))
    db.commit()
    return jsonify({"status": "success"})

@app.route('/api/rekap')
def api_rekap():
    db = get_db()
    total = db.execute("SELECT SUM(total_harga) FROM transaksi WHERE status = 'Selesai'").fetchone()[0] or 0
    riwayat = db.execute("SELECT * FROM transaksi ORDER BY waktu DESC").fetchall()
    grafik = db.execute("SELECT DATE(waktu) as tgl, SUM(total_harga) FROM transaksi WHERE status='Selesai' GROUP BY tgl LIMIT 7").fetchall()
    return jsonify({"total": total, "riwayat": [dict(row) for row in riwayat], "grafik": [{"tgl": r[0], "total": r[1]} for r in grafik]})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)