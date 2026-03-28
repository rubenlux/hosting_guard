import sqlite3

def check_db():
    conn = sqlite3.connect('audit_events.sqlite')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check users
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    print("--- USERS ---")
    for u in users:
        print(dict(u))
        
    # Check hostings
    cursor.execute("SELECT * FROM hostings")
    hostings = cursor.fetchall()
    print("\n--- HOSTINGS ---")
    for h in hostings:
        print(dict(h))
        
    conn.close()

if __name__ == "__main__":
    check_db()
