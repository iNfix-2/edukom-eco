import smtplib

print("--- TESTING TLS ON PORT 587 ---")
try:
    server = smtplib.SMTP('mail.edukom.ng', 587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login('support@edukom.ng', 'Johnokojere12395')
    print('TLS SUCCESS')
    server.quit()
except Exception as e:
    print('TLS FAILED:', e)

print("\n--- TESTING SSL ON PORT 465 ---")
try:
    server_ssl = smtplib.SMTP_SSL('mail.edukom.ng', 465)
    server_ssl.login('support@edukom.ng', 'Johnokojere12395')
    print('SSL SUCCESS')
    server_ssl.quit()
except Exception as e:
    print('SSL FAILED:', e)
