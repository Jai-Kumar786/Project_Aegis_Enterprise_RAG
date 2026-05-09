import os
import psycopg2
from dotenv import load_dotenv

def init_db():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    db_url = os.environ["NEON_DATABASE_URL"]
    
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        schema_sql = f.read()
        
    print("Connecting to Neon database...")
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            print("Applying schema (Dropping existing table if needed)...")
            cur.execute(schema_sql)
        conn.commit()
        print("Schema applied successfully! Table is now ready with VECTOR(1024).")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
