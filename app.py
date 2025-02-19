from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import os
from datetime import datetime, timedelta
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Mail ayarları
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "phrotexlegal@gmail.com"  # Gmail adresiniz
SMTP_PASSWORD = "uxoi oacr zorw tssa"      # Gmail uygulama şifresi

def get_db():
    conn = sqlite3.connect('meclis.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'user_id' in session:
        if session['role'] == 'admin':
            return redirect(url_for('admin_panel'))
        elif session['role'] == 'baskan':
            return redirect(url_for('baskan_panel'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['komisyon'] = user['komisyon']
            return redirect(url_for('index'))
            
        flash('Geçersiz kullanıcı adı veya şifre')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    db = get_db()
    baskanlar = db.execute('SELECT username, komisyon FROM users WHERE role = "baskan"').fetchall()
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        komisyon = request.form['komisyon']
        
        hashed_password = generate_password_hash(password)
        
        try:
            db.execute('INSERT INTO users (username, password, role, komisyon) VALUES (?, ?, ?, ?)',
                      (username, hashed_password, 'baskan', komisyon))
            db.execute('INSERT INTO komisyonlar (isim) VALUES (?)', (komisyon,))
            db.commit()
            flash('Başkan hesabı başarıyla oluşturuldu')
            return redirect(url_for('admin_panel'))
        except sqlite3.IntegrityError:
            flash('Bu kullanıcı adı zaten kullanılıyor')
        except:
            flash('Bir hata oluştu')
    
    return render_template('admin_panel.html', baskanlar=baskanlar)

@app.route('/ilk_giris', methods=['GET', 'POST'])
def ilk_giris():
    if 'user_id' not in session or session['role'] != 'baskan':
        return redirect(url_for('login'))
    
    db = get_db()
    komisyon = db.execute('SELECT * FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    if komisyon and komisyon['vekil_sayisi']:
        return redirect(url_for('baskan_panel'))
    
    if request.method == 'POST':
        vekil_sayisi = int(request.form['vekil_sayisi'])
        
        try:
            db.execute('UPDATE komisyonlar SET vekil_sayisi = ? WHERE isim = ?',
                      (vekil_sayisi, session['komisyon']))
            
            for i in range(vekil_sayisi):
                vekil_ismi = request.form[f'vekil_{i}']
                vekil_email = request.form[f'vekil_email_{i}']
                
                db.execute('''INSERT INTO milletvekilleri (isim, email, komisyon_id) 
                            VALUES (?, ?, ?)''',
                          (vekil_ismi, vekil_email, komisyon['id']))
            
            db.commit()
            return redirect(url_for('baskan_panel'))
        except:
            flash('Bir hata oluştu')
    
    return render_template('ilk_giris.html')

@app.route('/baskan_panel')
def baskan_panel():
    if 'user_id' not in session or session['role'] != 'baskan':
        return redirect(url_for('login'))
    
    db = get_db()
    komisyon = db.execute('SELECT * FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    if not komisyon or not komisyon['vekil_sayisi']:
        return redirect(url_for('ilk_giris'))
    
    # Son yoklamayı kontrol et
    son_yoklama = db.execute('''SELECT * FROM yoklama 
                               WHERE komisyon_id = ? 
                               ORDER BY tarih DESC LIMIT 1''',
                            (komisyon['id'],)).fetchone()
    
    # Aktif oturum bilgisi
    active_oturum = None
    if komisyon['oturum_suresi'] and komisyon['oturum_suresi'] > 0:
        # Eğer aktif oturum varsa, yeterli çoğunluk kontrolü yap
        if not son_yoklama or son_yoklama['mevcut_vekil'] <= son_yoklama['toplam_vekil'] // 2:
            # Yeterli çoğunluk yoksa oturumu sonlandır
            db.execute('''UPDATE komisyonlar 
                         SET oturum_konusu = NULL, oturum_suresi = 0 
                         WHERE isim = ?''',
                     (session['komisyon'],))
            db.commit()
        else:
            active_oturum = {
                'konu': komisyon['oturum_konusu'],
                'kalan_sure': komisyon['oturum_suresi']
            }
    
    # Milletvekilleri listesi (uyarı ve devamsızlık sayılarıyla)
    vekiller = db.execute('''SELECT m.*, 
                            COUNT(DISTINCT u.id) as uyari_sayisi,
                            COUNT(DISTINCT CASE WHEN yd.durum = 0 THEN y.id END) as devamsizlik
                            FROM milletvekilleri m
                            LEFT JOIN uyarilar u ON m.id = u.vekil_id
                            LEFT JOIN yoklama_detay yd ON m.id = yd.vekil_id
                            LEFT JOIN yoklama y ON yd.yoklama_id = y.id
                            WHERE m.komisyon_id = ?
                            GROUP BY m.id''',
                         (komisyon['id'],)).fetchall()
    
    # Önergeler listesi
    onergeler = db.execute('''SELECT o.*, m.isim as vekil_isim 
                             FROM onergeler o 
                             JOIN milletvekilleri m ON o.vekil_id = m.id
                             WHERE o.komisyon_id = ?
                             ORDER BY o.id DESC''',
                          (komisyon['id'],)).fetchall()
    
    return render_template('baskan_panel.html',
                         active_oturum=active_oturum,
                         vekiller=vekiller,
                         onergeler=onergeler)

@app.route('/oturum_baslat', methods=['POST'])
def oturum_baslat():
    if 'user_id' not in session or session['role'] != 'baskan':
        return redirect(url_for('login'))
    
    db = get_db()
    komisyon = db.execute('SELECT id FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    # Son yoklamayı kontrol et
    son_yoklama = db.execute('''SELECT * FROM yoklama 
                               WHERE komisyon_id = ? 
                               ORDER BY tarih DESC LIMIT 1''',
                            (komisyon['id'],)).fetchone()
    
    if not son_yoklama:
        flash('Oturum başlatmadan önce yoklama alınmalıdır')
        return redirect(url_for('baskan_panel'))
    
    # Yeterli çoğunluk kontrolü
    if son_yoklama['mevcut_vekil'] <= son_yoklama['toplam_vekil'] // 2:
        flash('Yeterli çoğunluk sağlanamadığı için oturum başlatılamaz')
        return redirect(url_for('baskan_panel'))
    
    konu = request.form['konu']
    sure = int(request.form['sure']) * 60  # Dakikayı saniyeye çevir
    
    db.execute('''UPDATE komisyonlar 
                  SET oturum_konusu = ?, oturum_suresi = ? 
                  WHERE isim = ?''',
              (konu, sure, session['komisyon']))
    db.commit()
    
    return redirect(url_for('baskan_panel'))

@app.route('/oturum_bitir', methods=['POST'])
def oturum_bitir():
    if 'user_id' not in session or session['role'] != 'baskan':
        return redirect(url_for('login'))
    
    db = get_db()
    komisyon = db.execute('SELECT * FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    # Son yoklamayı geçersiz kıl (yeni bir yoklama zorunlu olsun)
    db.execute('''INSERT INTO yoklama 
                  (komisyon_id, oturum_konusu, toplam_vekil, mevcut_vekil) 
                  VALUES (?, ?, ?, ?)''',
              (komisyon['id'], 'Oturum Sonlandırıldı', 0, 0))
    
    # Aktif oturumu sonlandır
    db.execute('''UPDATE komisyonlar 
                  SET oturum_konusu = NULL, oturum_suresi = 0 
                  WHERE isim = ?''',
              (session['komisyon'],))
    
    db.commit()
    return '', 200

@app.route('/onerge_ekle', methods=['POST'])
def onerge_ekle():
    if 'user_id' not in session or session['role'] != 'baskan':
        return redirect(url_for('login'))
    
    vekil_id = request.form['vekil_id']
    icerik = request.form['icerik']
    
    db = get_db()
    komisyon = db.execute('SELECT id, oturum_konusu FROM komisyonlar WHERE isim = ?',
                         (session['komisyon'],)).fetchone()
    
    if not komisyon['oturum_konusu']:
        flash('Aktif bir oturum olmadan önerge eklenemez')
        return redirect(url_for('baskan_panel'))
    
    db.execute('''INSERT INTO onergeler 
                  (icerik, vekil_id, komisyon_id, oturum_konusu)
                  VALUES (?, ?, ?, ?)''',
              (icerik, vekil_id, komisyon['id'], komisyon['oturum_konusu']))
    db.commit()
    
    return redirect(url_for('baskan_panel'))

@app.route('/oylama', methods=['POST'])
def oylama():
    if 'user_id' not in session or session['role'] != 'baskan':
        return '', 403
    
    data = request.get_json()
    onerge_id = data['onerge_id']
    evet = data['evet']
    hayir = data['hayir']
    
    db = get_db()
    db.execute('''UPDATE onergeler 
                  SET evet_oyu = ?, hayir_oyu = ?, oylanmis = 1
                  WHERE id = ?''',
              (evet, hayir, onerge_id))
    db.commit()
    
    return '', 200

@app.route('/yoklama_al', methods=['POST'])
def yoklama_al():
    if 'user_id' not in session or session['role'] != 'baskan':
        return '', 403
    
    data = request.get_json()
    vekil_durumlari = data['vekil_durumlari']
    
    db = get_db()
    komisyon = db.execute('SELECT * FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    mevcut_vekil = sum(1 for durum in vekil_durumlari.values() if durum)
    
    # Yoklama kaydı oluştur
    db.execute('''INSERT INTO yoklama 
                  (komisyon_id, oturum_konusu, toplam_vekil, mevcut_vekil)
                  VALUES (?, ?, ?, ?)''',
              (komisyon['id'], 'Yoklama Alındı', komisyon['vekil_sayisi'], mevcut_vekil))
    
    yoklama_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    for vekil_id, durum in vekil_durumlari.items():
        db.execute('''INSERT INTO yoklama_detay (yoklama_id, vekil_id, durum)
                     VALUES (?, ?, ?)''',
                  (yoklama_id, vekil_id, durum))
        
        # Yok yazılan vekillere mail gönder
        if not durum:
            vekil = db.execute('SELECT isim, email FROM milletvekilleri WHERE id = ?',
                             (vekil_id,)).fetchone()
            send_absence_mail(vekil['email'], vekil['isim'], 
                            komisyon['isim'], 
                            datetime.now().strftime('%d.%m.%Y %H:%M'))
    
    db.commit()
    
    return jsonify({
        'success': True,
        'yeterli_cogunluk': mevcut_vekil > komisyon['vekil_sayisi'] // 2
    })

@app.route('/yoklama_loglar')
def yoklama_loglar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    
    if session['role'] == 'admin':
        # Admin tüm komisyonların loglarını görebilir
        yoklamalar = db.execute('''
            SELECT y.*, k.isim as komisyon_adi,
                   GROUP_CONCAT(m.isim || ':' || yd.durum) as detaylar,
                   datetime(y.tarih, 'localtime') as formatli_tarih
            FROM yoklama y
            JOIN komisyonlar k ON y.komisyon_id = k.id
            LEFT JOIN yoklama_detay yd ON y.id = yd.yoklama_id
            LEFT JOIN milletvekilleri m ON yd.vekil_id = m.id
            GROUP BY y.id
            ORDER BY y.tarih DESC
        ''').fetchall()
    else:
        # Başkanlar sadece kendi komisyonlarının loglarını görebilir
        komisyon = db.execute('SELECT id FROM komisyonlar WHERE isim = ?', 
                            (session['komisyon'],)).fetchone()
        
        yoklamalar = db.execute('''
            SELECT y.*, k.isim as komisyon_adi,
                   GROUP_CONCAT(m.isim || ':' || yd.durum) as detaylar,
                   datetime(y.tarih, 'localtime') as formatli_tarih
            FROM yoklama y
            JOIN komisyonlar k ON y.komisyon_id = k.id
            LEFT JOIN yoklama_detay yd ON y.id = yd.yoklama_id
            LEFT JOIN milletvekilleri m ON yd.vekil_id = m.id
            WHERE y.komisyon_id = ?
            GROUP BY y.id
            ORDER BY y.tarih DESC
        ''', (komisyon['id'],)).fetchall()
    
    return render_template('yoklama_loglar.html', 
                         yoklamalar=yoklamalar, 
                         is_admin=session['role'] == 'admin')

@app.route('/son_yoklama')
def son_yoklama():
    if 'user_id' not in session or session['role'] != 'baskan':
        return '', 403
    
    db = get_db()
    komisyon = db.execute('SELECT id FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    son_yoklama = db.execute('''SELECT * FROM yoklama 
                               WHERE komisyon_id = ? 
                               ORDER BY tarih DESC LIMIT 1''',
                            (komisyon['id'],)).fetchone()
    
    return jsonify({
        'varsa': bool(son_yoklama),
        'yeterli_cogunluk': son_yoklama and son_yoklama['mevcut_vekil'] > son_yoklama['toplam_vekil'] // 2 if son_yoklama else False
    }) if son_yoklama else jsonify({'varsa': False})

@app.route('/uyari_ver', methods=['POST'])
def uyari_ver():
    if 'user_id' not in session or session['role'] != 'baskan':
        return '', 403
    
    data = request.get_json()
    vekil_id = data['vekil_id']
    sebep = data['sebep']
    
    db = get_db()
    komisyon = db.execute('SELECT id, isim FROM komisyonlar WHERE isim = ?', 
                         (session['komisyon'],)).fetchone()
    
    vekil = db.execute('SELECT isim, email FROM milletvekilleri WHERE id = ?',
                      (vekil_id,)).fetchone()
    
    db.execute('''INSERT INTO uyarilar (vekil_id, komisyon_id, sebep)
                  VALUES (?, ?, ?)''',
              (vekil_id, komisyon['id'], sebep))
    db.commit()
    
    # Mail gönder
    send_warning_mail(vekil['email'], vekil['isim'], komisyon['isim'], sebep)
    
    return '', 200

@app.route('/uyari_gecmisi/<int:vekil_id>')
def uyari_gecmisi(vekil_id):
    if 'user_id' not in session:
        return '', 403
    
    db = get_db()
    
    if session['role'] == 'admin':
        uyarilar = db.execute('''SELECT u.*, k.isim as komisyon_adi,
                                datetime(u.tarih, 'localtime') as formatli_tarih
                                FROM uyarilar u
                                JOIN komisyonlar k ON u.komisyon_id = k.id
                                WHERE u.vekil_id = ?
                                ORDER BY u.tarih DESC''',
                            (vekil_id,)).fetchall()
    else:
        komisyon = db.execute('SELECT id FROM komisyonlar WHERE isim = ?', 
                            (session['komisyon'],)).fetchone()
        
        uyarilar = db.execute('''SELECT u.*, k.isim as komisyon_adi,
                                datetime(u.tarih, 'localtime') as formatli_tarih
                                FROM uyarilar u
                                JOIN komisyonlar k ON u.komisyon_id = k.id
                                WHERE u.vekil_id = ? AND u.komisyon_id = ?
                                ORDER BY u.tarih DESC''',
                            (vekil_id, komisyon['id'])).fetchall()
    
    return jsonify([dict(u) for u in uyarilar])

@app.route('/admin_uyarilar')
def admin_uyarilar():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    db = get_db()
    
    # Tüm uyarıları komisyon ve vekil bilgileriyle birlikte getir
    uyarilar = db.execute('''
        SELECT u.*, 
               m.isim as vekil_isim,
               k.isim as komisyon_adi,
               datetime(u.tarih, 'localtime') as formatli_tarih
        FROM uyarilar u
        JOIN milletvekilleri m ON u.vekil_id = m.id
        JOIN komisyonlar k ON u.komisyon_id = k.id
        ORDER BY u.tarih DESC
    ''').fetchall()
    
    # Vekillerin devamsızlık sayılarını getir
    devamsizliklar = db.execute('''
        SELECT m.id, m.isim as vekil_isim, 
               k.isim as komisyon_adi,
               COUNT(CASE WHEN yd.durum = 0 THEN 1 END) as devamsizlik_sayisi,
               COUNT(DISTINCT y.id) as toplam_yoklama
        FROM milletvekilleri m
        JOIN komisyonlar k ON m.komisyon_id = k.id
        LEFT JOIN yoklama_detay yd ON m.id = yd.vekil_id
        LEFT JOIN yoklama y ON yd.yoklama_id = y.id
        GROUP BY m.id
        HAVING devamsizlik_sayisi > 0
        ORDER BY devamsizlik_sayisi DESC
    ''').fetchall()
    
    return render_template('admin_uyarilar.html', 
                         uyarilar=uyarilar,
                         devamsizliklar=devamsizliklar)

def get_mail_template(content):
    return f"""
    <html>
        <head>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    font-family: Arial, sans-serif;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #34495e;
                    padding: 20px;
                    text-align: center;
                }}
                .header img {{
                    height: 80px;
                    margin-bottom: 10px;
                    border-radius: 50%;
                }}
                .header h1 {{
                    color: white;
                    margin: 0;
                    font-size: 24px;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #666;
                    font-size: 14px;
                    border-top: 1px solid #eee;
                }}
                .warning {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeeba;
                    color: #856404;
                    padding: 15px;
                    border-radius: 4px;
                    margin: 20px 0;
                }}
                .button {{
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #34495e;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body style="background-color: #f5f7fa;">
            <div class="container">
                <div class="header">
                    <img src="https://i.hizliresim.com/1dl6c50.jpg" alt="MPAL Meclis Logo">
                    <h1>MPAL Meclis Simülasyonu</h1>
                </div>
                <div class="content">
                    {content}
                    <div class="warning">
                        Bu maili spam olarak işaretlememek için lütfen phrotexlegal@gmail.com adresini güvenilir gönderenler listenize ekleyin.
                    </div>
                </div>
                <div class="footer">
                    <p>Bu mail otomatik olarak gönderilmiştir, lütfen yanıtlamayınız.</p>
                    <p>İletişim: phrotexlegal@gmail.com</p>
                    <p>© 2024 MPAL Meclis Simülasyonu. Tüm hakları saklıdır.</p>
                </div>
            </div>
        </body>
    </html>
    """

def send_warning_mail(vekil_email, vekil_isim, komisyon, sebep):
    subject = f"MPAL Meclis Simülasyonu - {komisyon} Komisyonu Uyarı Bildirimi"
    
    content = f"""
    <h2>Sayın {vekil_isim},</h2>
    <p>Bu mail MPAL Meclis Simülasyonu sisteminden otomatik olarak gönderilmiştir.</p>
    <p><strong>{komisyon} Komisyonu</strong>'nda aşağıdaki sebepten dolayı uyarı aldınız:</p>
    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 4px; margin: 15px 0;">
        {sebep}
    </div>
    <p>Saygılarımızla,<br>MPAL Meclis Simülasyonu Yönetimi</p>
    """
    
    html_content = get_mail_template(content)
    return send_mail(vekil_email, subject, html_content)

def send_absence_mail(vekil_email, vekil_isim, komisyon, tarih):
    subject = f"MPAL Meclis Simülasyonu - {komisyon} Komisyonu Devamsızlık Bildirimi"
    
    content = f"""
    <h2>Sayın {vekil_isim},</h2>
    <p>Bu mail MPAL Meclis Simülasyonu sisteminden otomatik olarak gönderilmiştir.</p>
    <p><strong>{komisyon} Komisyonu</strong>'nun {tarih} tarihli oturumunda yok olarak işaretlendiniz.</p>
    <p>Saygılarımızla,<br>MPAL Meclis Simülasyonu Yönetimi</p>
    """
    
    html_content = get_mail_template(content)
    return send_mail(vekil_email, subject, html_content)

def send_mail(to_email, subject, html_content):
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"MPAL Meclis Simülasyonu <{SMTP_USERNAME}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Düz metin versiyonu (HTML'den temizlenmiş)
        text_content = html_content.replace('<br>', '\n')
        text_content = re.sub('<[^<]+?>', '', text_content)
        text_part = MIMEText(text_content, 'plain', 'utf-8')
        
        # HTML versiyonu
        html_part = MIMEText(html_content, 'html', 'utf-8')
        
        # Önce text, sonra html ekle (mail istemcileri hangisini göstereceğine karar versin)
        msg.attach(text_part)
        msg.attach(html_part)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Mail gönderme hatası: {e}")
        return False

if __name__ == '__main__':
    app.run(debug=True) 