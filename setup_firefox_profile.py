import os
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

profile_path = os.path.join(os.getcwd(), "firefox_cms_profile")
if not os.path.exists(profile_path):
    os.makedirs(profile_path)

options = Options()
options.profile = profile_path

driver = webdriver.Firefox(options=options)
# Mengarahkan langsung ke URL admin livestreamings yang benar
driver.get("https://www.vidio.com/admin/livestreamings")

input("Pastikan halaman Admin Livestreamings sudah terbuka sempurna di Firefox. Jika sudah, tekan ENTER di terminal ini...")
driver.quit()
print("Selesai! Sesi login CMS tersimpan aman di folder 'firefox_cms_profile'.")