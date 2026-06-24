import os

files_public = [
    r'c:\Users\ASUS\Desktop\Vektia\public\index.html',
    r'c:\Users\ASUS\Desktop\Vektia\public\terms.html',
    r'c:\Users\ASUS\Desktop\Vektia\public\privacy.html'
]

for f in files_public:
    with open(f, 'r', encoding='utf-8') as file:
        data = file.read()
    data = data.replace('src="logo.png"', 'src="/logo.png"')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(data)

files_admin = [
    r'c:\Users\ASUS\Desktop\Vektia\admin\login.html',
    r'c:\Users\ASUS\Desktop\Vektia\admin\customer_login.html',
    r'c:\Users\ASUS\Desktop\Vektia\admin\js\layout.js'
]

for f in files_admin:
    with open(f, 'r', encoding='utf-8') as file:
        data = file.read()
    data = data.replace('src="../public/logo.png"', 'src="/logo.png"')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(data)

print('Restored all logo paths to /logo.png')
