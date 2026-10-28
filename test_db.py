
import os
import mysql.connector

try:
    connection = mysql.connector.connect(
        host="127.0.0.1",
        port=3306,
        user="pawhaven_app",
        password=os.environ["DB_PASSWORD"],
        database="pawhaven_db"
    )

    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")

    print("Connected to PawHaven MySQL successfully!")
    print("Tables in database:")

    for row in cursor.fetchall():
        print("-", row[0])

    cursor.close()
    connection.close()

except Exception as error:
    print("Database connection failed:", error)
