import sqlite3

def check_db():
    conn = sqlite3.connect('meclis.db')
    c = conn.cursor()
    
    # Tabloları listele
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = c.fetchall()
    print("Mevcut tablolar:", tables)
    
    # Admin kullanıcısını kontrol et
    c.execute("SELECT * FROM users WHERE username='admin';")
    admin = c.fetchone()
    print("Admin kullanıcısı:", admin)
    
    conn.close()

if __name__ == '__main__':
    check_db() 