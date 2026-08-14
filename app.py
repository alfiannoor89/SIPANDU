
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3, csv, io
from datetime import datetime
from functools import wraps

app=Flask(__name__); app.secret_key="sipandu-kotabaru-2026"
DB="sipandu.db"; ADMIN_USER="admin"; ADMIN_PASS="sipandu2026"
UNSUR=[("kecepatan","Kecepatan Pelayanan"),("ketepatan","Ketepatan Pelayanan"),("keramahan","Keramahan Petugas"),("kemudahan","Kemudahan Prosedur"),("kedisiplinan","Kedisiplinan Pelayanan"),("respons","Respons terhadap Kebutuhan Pegawai"),("komunikasi","Kualitas Komunikasi Pelayanan"),("kepuasan","Kepuasan Pelayanan Secara Umum")]

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def cols(c,t): return [x["name"] for x in c.execute(f"PRAGMA table_info({t})").fetchall()]
def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS penilaian(id INTEGER PRIMARY KEY AUTOINCREMENT,tanggal TEXT,bidang TEXT,nama TEXT,jenis_kelamin TEXT,lama_bekerja TEXT,jenis_pelayanan TEXT,kecepatan INTEGER,ketepatan INTEGER,keramahan INTEGER,kemudahan INTEGER,kedisiplinan INTEGER,respons INTEGER,komunikasi INTEGER,kepuasan INTEGER,kritik TEXT,saran TEXT,aduan TEXT,status_aduan TEXT DEFAULT 'Baru',tindak_lanjut TEXT DEFAULT '',tahun INTEGER)""")
    if "tahun" not in cols(c,"penilaian"): c.execute("ALTER TABLE penilaian ADD COLUMN tahun INTEGER")
    c.execute("UPDATE penilaian SET tahun=CAST(substr(tanggal,1,4) AS INTEGER) WHERE tahun IS NULL")
    c.execute("""CREATE TABLE IF NOT EXISTS aduan(id INTEGER PRIMARY KEY AUTOINCREMENT,tanggal TEXT,tahun INTEGER,nama TEXT,bidang TEXT,jenis_pelayanan TEXT,isi TEXT,status TEXT DEFAULT 'Baru',tindak_lanjut TEXT DEFAULT '')""")
    # migrasi aduan lama agar tidak hilang
    c.execute("""INSERT INTO aduan(tanggal,tahun,nama,bidang,jenis_pelayanan,isi,status,tindak_lanjut)
    SELECT tanggal,COALESCE(tahun,CAST(substr(tanggal,1,4) AS INTEGER)),nama,bidang,jenis_pelayanan,aduan,status_aduan,tindak_lanjut
    FROM penilaian p WHERE TRIM(COALESCE(aduan,''))<>'' AND NOT EXISTS
    (SELECT 1 FROM aduan a WHERE a.tanggal=p.tanggal AND a.nama=p.nama AND a.isi=p.aduan)""")
    c.commit(); c.close()
@app.context_processor
def inject(): return dict(UNSUR=UNSUR)
def admin_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("admin"): return redirect(url_for("login"))
        return f(*a,**k)
    return w
@app.route("/")
def index(): return render_template("index.html")
@app.route("/survei",methods=["GET","POST"])
def survei():
    tahun=datetime.now().year
    if request.method=="POST":
        f=request.form; scores=[int(f[k]) for k,_ in UNSUR]
        c=db(); c.execute("""INSERT INTO penilaian(tanggal,tahun,bidang,nama,jenis_kelamin,lama_bekerja,jenis_pelayanan,kecepatan,ketepatan,keramahan,kemudahan,kedisiplinan,respons,komunikasi,kepuasan,kritik,saran)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",[datetime.now().strftime("%Y-%m-%d %H:%M:%S"),tahun,f["bidang"],f["nama"],f["jenis_kelamin"],f["lama_bekerja"],f["jenis_pelayanan"]]+scores+[f.get("kritik",""),f.get("saran","")]); c.commit(); c.close()
        return render_template("sukses.html",jenis="survei")
    return render_template("survei.html",tahun=tahun)
@app.route("/aduan",methods=["GET","POST"])
def form_aduan():
    tahun=datetime.now().year
    if request.method=="POST":
        f=request.form; c=db(); c.execute("INSERT INTO aduan(tanggal,tahun,nama,bidang,jenis_pelayanan,isi) VALUES(?,?,?,?,?,?)",(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),tahun,f["nama"],f["bidang"],f["jenis_pelayanan"],f["isi"])); c.commit(); c.close()
        return render_template("sukses.html",jenis="aduan")
    return render_template("form_aduan.html",tahun=tahun)
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form.get("username")==ADMIN_USER and request.form.get("password")==ADMIN_PASS: session["admin"]=True; return redirect(url_for("dashboard"))
        flash("Username atau password salah.")
    return render_template("login.html")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("index"))
def tahun_list(c):
    ys=[r[0] for r in c.execute("SELECT DISTINCT tahun FROM penilaian WHERE tahun IS NOT NULL ORDER BY tahun DESC").fetchall()]
    y=datetime.now().year
    return ys if ys else [y]
@app.route("/admin")
@admin_required
def dashboard():
    c=db(); years=tahun_list(c); tahun=request.args.get("tahun",type=int) or years[0]
    rows=c.execute("SELECT * FROM penilaian WHERE tahun=? ORDER BY id DESC",(tahun,)).fetchall(); total=len(rows)
    avg=round(sum(sum(r[k] for k,_ in UNSUR) for r in rows)/(total*8),2) if total else 0
    per_unsur={label:round(sum(r[k] for r in rows)/total,2) if total else 0 for k,label in UNSUR}
    dist={i:sum(1 for r in rows if r["kepuasan"]==i) for i in range(1,6)}
    layanan=c.execute("SELECT jenis_pelayanan,COUNT(*) jumlah FROM penilaian WHERE tahun=? GROUP BY jenis_pelayanan",(tahun,)).fetchall()
    aduan=c.execute("SELECT COUNT(*) n FROM aduan WHERE tahun=?",(tahun,)).fetchone()["n"]; baru=c.execute("SELECT COUNT(*) n FROM aduan WHERE tahun=? AND status='Baru'",(tahun,)).fetchone()["n"]; c.close()
    return render_template("dashboard.html",rows=rows[:10],total=total,avg=avg,per_unsur=per_unsur,dist=dist,layanan=layanan,aduan=aduan,baru=baru,tahun=tahun,years=years)
@app.route("/admin/data")
@admin_required
def data():
    c=db(); years=tahun_list(c); tahun=request.args.get("tahun",type=int) or years[0]; q=request.args.get("q","").strip()
    sql="SELECT * FROM penilaian WHERE tahun=?"; par=[tahun]
    if q: sql+=" AND (nama LIKE ? OR bidang LIKE ? OR jenis_pelayanan LIKE ?)"; par += ["%"+q+"%"]*3
    rows=c.execute(sql+" ORDER BY id DESC",par).fetchall(); c.close()
    return render_template("data.html",rows=rows,q=q,tahun=tahun,years=years)
@app.route("/admin/aduan")
@admin_required
def aduan():
    c=db(); years=sorted(set(tahun_list(c)+[r[0] for r in c.execute("SELECT DISTINCT tahun FROM aduan WHERE tahun IS NOT NULL").fetchall()]),reverse=True); tahun=request.args.get("tahun",type=int) or years[0]
    rows=c.execute("SELECT * FROM aduan WHERE tahun=? ORDER BY id DESC",(tahun,)).fetchall(); c.close()
    return render_template("aduan.html",rows=rows,tahun=tahun,years=years)
@app.route("/admin/aduan/<int:id>",methods=["POST"])
@admin_required
def aduan_update(id):
    c=db(); c.execute("UPDATE aduan SET status=?,tindak_lanjut=? WHERE id=?",(request.form["status"],request.form["tindak_lanjut"],id)); c.commit(); c.close(); flash("Tindak lanjut aduan berhasil diperbarui."); return redirect(request.referrer or url_for("aduan"))
@app.route("/admin/laporan")
@admin_required
def laporan():
    c=db(); years=tahun_list(c); tahun=request.args.get("tahun",type=int) or years[0]; rows=c.execute("SELECT * FROM penilaian WHERE tahun=?",(tahun,)).fetchall(); total=len(rows)
    avg=round(sum(sum(r[k] for k,_ in UNSUR) for r in rows)/(total*8),2) if total else 0
    per_unsur={label:round(sum(r[k] for r in rows)/total,2) if total else 0 for k,label in UNSUR}
    dist={i:sum(1 for r in rows if r["kepuasan"]==i) for i in range(1,6)}
    layanan=c.execute("SELECT jenis_pelayanan,COUNT(*) jumlah,ROUND(AVG(kepuasan),2) rata FROM penilaian WHERE tahun=? GROUP BY jenis_pelayanan",(tahun,)).fetchall(); c.close()
    kategori="Sangat Puas" if avg>=4.21 else "Puas" if avg>=3.41 else "Cukup Puas" if avg>=2.61 else "Tidak Puas" if avg>=1.81 else "Sangat Tidak Puas"
    return render_template("laporan.html",tahun=tahun,years=years,total=total,avg=avg,kategori=kategori,per_unsur=per_unsur,dist=dist,layanan=layanan)
@app.route("/admin/export")
@admin_required
def export():
    tahun=request.args.get("tahun",type=int) or datetime.now().year; c=db(); rows=c.execute("SELECT * FROM penilaian WHERE tahun=? ORDER BY id",(tahun,)).fetchall(); c.close()
    out=io.StringIO(); w=csv.writer(out)
    if rows: w.writerow(rows[0].keys()); [w.writerow(list(r)) for r in rows]
    return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")),mimetype="text/csv",as_attachment=True,download_name=f"laporan_sipandu_{tahun}.csv")
if __name__=="__main__": init_db(); app.run(host="0.0.0.0",port=5000,debug=True)
