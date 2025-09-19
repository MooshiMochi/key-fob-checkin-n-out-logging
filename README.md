# ------------------------------

# File: README.md (quick start)

# ------------------------------

#

# Features

# - Check-out requires employee card tap first (20s window).

# - After first key checkout, employee has 2 minutes to check out more keys without re-tapping.

# - Check-in requires only the key fob tap, but only after the key has been out for at least 2 minutes.

# - Simple PySide6 UI you can debug on your PC: shows currently checked-out keys, a menu button (top-right)

# for Register Employee, Register Key, and Print Logs (CSV for a date/time range).

# - SQLite database, safe concurrency, audit logs.

# - RC522 abstraction with real-hardware adapter and a Mock adapter for desktop testing.

# - Employee names stored on card as AES-GCM ciphertext using a secret key.

#

# Wiring (RPi)

# - Uses SPI. Enable SPI: `sudo raspi-config` → Interface Options → SPI → Enable.

# - Typical RC522 ↔ RPi pins (BCM):

# SDA/SS → GPIO8 (CE0)

# SCK → GPIO11 (SCLK)

# MOSI → GPIO10 (MOSI)

# MISO → GPIO9 (MISO)

# RST → GPIO25 (configurable)

# 3.3V → 3V3, GND → GND

#

# Run (desktop mock):

# python -m app --mock

# In the UI, use the ⋮ menu → Register... to create entries. Then use the

# mock input box (bottom) to simulate RFID UIDs like `emp:DE:AD:BE:EF` or `key:AA:BB:CC:DD`.

#

# Run (on Pi with real reader):

# python -m app

#

# Export logs:

# Use menu → Print/Export Logs → pick date range → CSV file is saved to ./exports/

#

# Dependencies

# pip install PySide6 cryptography mfrc522 spidev RPi.GPIO

# (On desktop mock, you only need PySide6 and cryptography.)

#

# Security note

# - MIFARE Classic + RC522 is not strong security. We encrypt the name on-card (AES-GCM),

# but do not rely on the card for strong authentication.
