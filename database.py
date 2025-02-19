import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('meclis.db')
    c = conn.cursor()
    
    # Kullanıcılar tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT NOT NULL,
                  komisyon TEXT)''')
    
    # Komisyonlar tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS komisyonlar
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  isim TEXT NOT NULL,
                  vekil_sayisi INTEGER,
                  oturum_konusu TEXT,
                  oturum_suresi INTEGER)''')
    
    # Milletvekilleri tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS milletvekilleri
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  isim TEXT NOT NULL,
                  email TEXT NOT NULL,
                  komisyon_id INTEGER,
                  FOREIGN KEY(komisyon_id) REFERENCES komisyonlar(id))''')
    
    # Önergeler tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS onergeler
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  icerik TEXT NOT NULL,
                  vekil_id INTEGER,
                  komisyon_id INTEGER,
                  oturum_konusu TEXT,
                  evet_oyu INTEGER DEFAULT 0,
                  hayir_oyu INTEGER DEFAULT 0,
                  oylanmis BOOLEAN DEFAULT 0,
                  FOREIGN KEY(vekil_id) REFERENCES milletvekilleri(id),
                  FOREIGN KEY(komisyon_id) REFERENCES komisyonlar(id))''')
    
    # Yoklama tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS yoklama
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  komisyon_id INTEGER,
                  oturum_konusu TEXT,
                  tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  toplam_vekil INTEGER,
                  mevcut_vekil INTEGER,
                  FOREIGN KEY(komisyon_id) REFERENCES komisyonlar(id))''')
    
    # Yoklama detay tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS yoklama_detay
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  yoklama_id INTEGER,
                  vekil_id INTEGER,
                  durum BOOLEAN,
                  FOREIGN KEY(yoklama_id) REFERENCES yoklama(id),
                  FOREIGN KEY(vekil_id) REFERENCES milletvekilleri(id))''')
    
    # Uyarı tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS uyarilar
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  vekil_id INTEGER,
                  komisyon_id INTEGER,
                  sebep TEXT,
                  tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(vekil_id) REFERENCES milletvekilleri(id),
                  FOREIGN KEY(komisyon_id) REFERENCES komisyonlar(id))''')
    
    # Admin hesabını oluştur
    admin_password = generate_password_hash('admin123')
    c.execute('INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)',
              ('admin', admin_password, 'admin'))
    
    conn.commit()
    conn.close()

def update_db():
    conn = sqlite3.connect('meclis.db')
    c = conn.cursor()
    
    try:
        c.execute('''ALTER TABLE onergeler 
                     ADD COLUMN oturum_konusu TEXT''')
        conn.commit()
    except:
        pass  # Sütun zaten varsa hata vermesini engelle
    
    conn.close()

if __name__ == '__main__':
    init_db() 