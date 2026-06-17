from server.app import app

with app.test_client() as c:
    res = c.post('/api/login', json={'usuario': 'admin', 'password': 'admin123'})
    print('login', res.status_code)
    print(res.data.decode('utf-8'))
    print('cookies', res.headers.get_all('Set-Cookie'))
    if res.status_code == 200:
        cookie = res.headers.get_all('Set-Cookie')[0].split(';', 1)[0]
        res2 = c.get('/api/whoami', headers={'Cookie': cookie})
        print('whoami', res2.status_code)
        print(res2.data.decode('utf-8'))
