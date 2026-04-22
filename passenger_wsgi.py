import os
import sys

# Mengarahkan jalur Python agar bisa membaca file app.py di dalam direktori saat ini
sys.path.insert(0, os.path.dirname(__file__))

# Mengimpor objek 'app' dari app.py dan mengganti namanya menjadi 'application'
# Ini adalah standar yang diminta oleh cPanel / Phusion Passenger
from app import app as application
